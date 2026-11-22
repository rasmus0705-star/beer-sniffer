import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("DB_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Beer, Price, PriceAlert, PriceHistory
from app.services.ingest import ingest_batch
from app.utils.scrape_cache import load_shop_cache, save_shop_cache, seed_shop_caches_from_snapshot
from app.utils import shopify


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = 0

    def get(self, _url, timeout):
        self.calls += 1
        self.assert_timeout = timeout
        return self.responses.pop(0)


class ShopifyResilienceTests(unittest.TestCase):
    def test_cache_marks_fallback_and_rejects_older_than_14_days(self):
        now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        product = {"name": "Test Beer", "price": 20, "shop_name": "A Good Case"}
        with tempfile.TemporaryDirectory() as temp:
            save_shop_cache("A Good Case", [product], cache_dir=temp, now=now - timedelta(days=14))
            cached = load_shop_cache("A Good Case", cache_dir=temp, now=now)
            self.assertIsNotNone(cached)
            self.assertTrue(cached[0][0]["_stale_cache"])

            save_shop_cache("A Good Case", [product], cache_dir=temp, now=now - timedelta(days=14, seconds=1))
            self.assertIsNone(load_shop_cache("A Good Case", cache_dir=temp, now=now))

    def test_recent_data_snapshot_seeds_only_fresh_shop_prices(self):
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            snapshot_path = os.path.join(temp, "data.json")
            with open(snapshot_path, "w", encoding="utf-8") as file:
                json.dump({
                    "updated_at": "2026-11-01T12:00:00+00:00",
                    "beers": [
                        {"name": "Fresh Snapshot Beer", "prices": [{
                            "shop_name": "A Good Case", "price": 20, "url": "https://shop.test/fresh",
                        }]},
                        {"name": "Old Marked Price", "prices": [{
                            "shop_name": "A Good Case", "price": 10, "stale": True,
                        }]},
                    ],
                }, file)
            seeded = seed_shop_caches_from_snapshot(
                ["A Good Case"], snapshot_path=snapshot_path,
                cache_dir=os.path.join(temp, "cache"), now=now,
            )
            self.assertEqual(seeded, {"A Good Case": 1})
            cached, fetched_at = load_shop_cache(
                "A Good Case", cache_dir=os.path.join(temp, "cache"), now=now,
            )
            self.assertEqual(cached[0]["name"], "Fresh Snapshot Beer")
            self.assertEqual(fetched_at, "2026-11-01T12:00:00+00:00")

    def test_shopify_retries_once_using_retry_after(self):
        session = FakeSession([
            FakeResponse(429, headers={"Retry-After": "7"}),
            FakeResponse(200, {"products": [{"title": "Beer"}]}),
        ])
        with patch.object(shopify.requests, "Session", return_value=session), \
             patch.object(shopify.time, "sleep") as sleep:
            pages = list(shopify.shopify_pages("https://shop.test", "Shop", {}, limit=250))
        self.assertEqual(pages, [(1, [{"title": "Beer"}])])
        self.assertEqual(session.calls, 2)
        sleep.assert_called_once_with(7)

    def test_second_429_raises_with_shop_and_page_metadata(self):
        session = FakeSession([
            FakeResponse(429, headers={"Retry-After": "0"}),
            FakeResponse(429, headers={"Retry-After": "0"}),
        ])
        with patch.object(shopify.requests, "Session", return_value=session), \
             patch.object(shopify.time, "sleep"):
            with self.assertRaises(shopify.ShopifyFejl) as caught:
                list(shopify.shopify_pages("https://shop.test", "Shop", {}, limit=250))
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.page, 1)

    def test_429_error_includes_shopify_bot_filter_diagnostics(self):
        session = FakeSession([
            FakeResponse(429, headers={"Retry-After": "0", "X-Request-Id": "req-123"},
                         text="local_rate_limited"),
            FakeResponse(429, headers={"Retry-After": "0", "CF-Ray": "ray-456"},
                         text="local_rate_limited"),
        ])
        with patch.object(shopify.requests, "Session", return_value=session), \
             patch.object(shopify.time, "sleep"):
            with self.assertRaises(shopify.ShopifyFejl) as caught:
                list(shopify.shopify_pages("https://shop.test", "Shop", {}, limit=250))
        self.assertIn("local_rate_limited", str(caught.exception))
        self.assertIn("X-Request-Id=req-123", str(caught.exception))

    def test_stale_products_do_not_add_price_history_or_trigger_alerts(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        try:
            with Session() as db:
                db.add(Beer(id=1, name="Test Rum Porter", normalized_name="test rum porter",
                            slug="test-rum-porter", volume_cl=33, abv=5.0))
                db.add(PriceHistory(id=1, beer_id=1, shop_name="A Good Case", price_dkk=25.0))
                db.add(PriceAlert(id=1, beer_id=1, target_price=30.0,
                                  email="test@example.test", active=True))
                db.commit()
                ingest_batch(db, [{
                    "name": "Test Rum Porter", "price": 15.0, "shop_name": "A Good Case",
                    "volume_cl": 33, "abv": 5.0, "_stale_cache": True,
                }])
                self.assertEqual(db.query(PriceHistory).count(), 1)
                self.assertTrue(db.query(PriceAlert).one().active)
                self.assertEqual(db.query(Price).one().price_dkk, 15.0)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
