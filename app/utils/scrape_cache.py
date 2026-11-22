"""Short-lived per-shop cache used when a live Shopify scrape is throttled."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import tempfile
import unicodedata

CACHE_MAX_AGE = timedelta(days=14)


def _shop_key(shop):
    value = unicodedata.normalize("NFKD", shop).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "shop"


def _cache_path(shop, cache_dir=None):
    root = Path(cache_dir) if cache_dir is not None else Path.cwd() / "cache" / "shops"
    return root / f"{_shop_key(shop)}.json"


def save_shop_cache(shop, products, *, cache_dir=None, now=None):
    """Atomically save a successful live result; never overwrite with fallback data."""
    fresh = [deepcopy(item) for item in products if not item.get("_stale_cache")]
    if not fresh:
        return None
    fetched_at = now or datetime.now(timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    fetched_text = fetched_at.astimezone(timezone.utc).isoformat(timespec="seconds")
    path = _cache_path(shop, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"hentet": fetched_text, "produkter": fresh}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name + ".", suffix=".tmp", delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False)
        temp_path = Path(tmp.name)
    temp_path.replace(path)
    return fetched_text


def load_shop_cache(shop, *, cache_dir=None, now=None, max_age=CACHE_MAX_AGE):
    """Return (marked_products, fetched_at) when the cache is valid and <=14 days old."""
    path = _cache_path(shop, cache_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["hentet"])
        products = payload["produkter"]
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        age = current - fetched_at
        if age < timedelta(minutes=-5) or age > max_age or not isinstance(products, list) or not products:
            return None
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None

    fetched_text = fetched_at.astimezone(timezone.utc).isoformat(timespec="seconds")
    result = []
    for item in products:
        if not isinstance(item, dict):
            continue
        marked = deepcopy(item)
        marked["_stale_cache"] = True
        marked["_cache_fetched_at"] = fetched_text
        result.append(marked)
    return (result, fetched_text) if result else None


def seed_shop_caches_from_snapshot(shops=None, *, snapshot_path="data.json", cache_dir=None, now=None):
    """Seed per-shop caches from the last good generated snapshot, if it is recent."""
    try:
        snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        updated_at = datetime.fromisoformat(snapshot["updated_at"])
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=datetime.now().astimezone().tzinfo)
        updated_at = updated_at.astimezone(timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        age = current - updated_at
        if age < timedelta(minutes=-5) or age > CACHE_MAX_AGE:
            return {}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {}

    selected = set(shops) if shops is not None else None
    grouped = {}
    beer_fields = ("name", "brewery", "volume_cl", "abv", "type", "image", "description", "category")
    for beer in snapshot.get("beers", []):
        if not isinstance(beer, dict):
            continue
        common = {key: beer[key] for key in beer_fields if key in beer}
        for price in beer.get("prices", []):
            if not isinstance(price, dict) or price.get("stale"):
                continue
            shop = price.get("shop_name")
            if not shop or (selected is not None and shop not in selected):
                continue
            grouped.setdefault(shop, []).append({**common, **price})

    seeded = {}
    for shop, products in grouped.items():
        path = _cache_path(shop, cache_dir)
        existing_at = None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            existing_at = datetime.fromisoformat(payload["hentet"])
            if existing_at.tzinfo is None:
                existing_at = existing_at.replace(tzinfo=timezone.utc)
            existing_at = existing_at.astimezone(timezone.utc)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass
        if existing_at is not None and existing_at >= updated_at:
            continue
        fetched_at = save_shop_cache(shop, products, cache_dir=cache_dir, now=updated_at)
        if fetched_at:
            seeded[shop] = len(products)
    return seeded
