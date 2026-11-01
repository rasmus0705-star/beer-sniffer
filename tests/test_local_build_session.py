import os
import io
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from unittest.mock import patch

os.environ.setdefault("DB_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import build_data
from app.database import Base
from app.models import Beer, Price, PriceAlert, PriceHistory
from app.utils.utc import utcnow_naive


class LocalBuildSessionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

        with self.session_factory() as db:
            db.add(Beer(
                id=1,
                name="Test Rum Porter",
                normalized_name="test rum porter",
                slug="test-rum-porter",
                volume_cl=33,
                abv=5.0,
            ))
            db.add(Price(
                id=1,
                beer_id=1,
                shop_name="Test Shop",
                price_dkk=25.0,
                url="https://example.test/beer",
                available=True,
            ))
            now = utcnow_naive()
            db.add_all([
                PriceHistory(
                    id=1, beer_id=1, shop_name="Test Shop", price_dkk=20.0,
                    created_at=now - timedelta(days=200),
                ),
                PriceHistory(
                    id=2, beer_id=1, shop_name="Test Shop", price_dkk=25.0,
                    created_at=now - timedelta(days=1),
                ),
                PriceHistory(
                    id=3, beer_id=1, shop_name="Legacy Shop", price_dkk=22.0,
                    created_at=now - timedelta(days=200),
                ),
            ])
            db.add(PriceAlert(
                id=1,
                beer_id=1,
                target_price=15.0,
                email="test@example.test",
                active=True,
            ))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_ingest_changes_only_the_local_snapshot(self):
        with redirect_stdout(io.StringIO()):
            with patch.object(build_data, "SessionLocal", self.session_factory):
                with build_data.build_session(no_db_write=True) as local_db:
                    self.assertEqual(local_db.query(Beer).count(), 1)
                    self.assertEqual(local_db.query(Price).count(), 1)
                    # Includes recent history and the latest older row per shop.
                    self.assertEqual(local_db.query(PriceHistory).count(), 2)
                    self.assertEqual(local_db.query(PriceAlert).count(), 1)

                    local_db.query(Price).filter_by(shop_name="Test Shop").delete(
                        synchronize_session=False
                    )
                    local_db.add(Price(
                        beer_id=1,
                        shop_name="Test Shop",
                        price_dkk=30.0,
                        url="https://example.test/beer",
                        available=True,
                    ))
                    local_db.commit()
                    self.assertEqual(
                        local_db.query(Price).one().price_dkk,
                        30.0,
                    )

        with self.session_factory() as source_db:
            self.assertEqual(source_db.query(Price).count(), 1)
            self.assertEqual(source_db.query(Price).one().price_dkk, 25.0)
            self.assertEqual(source_db.query(PriceHistory).count(), 3)
            self.assertTrue(source_db.query(PriceAlert).one().active)


if __name__ == "__main__":
    unittest.main()
