from rapidfuzz import fuzz
from sqlalchemy.orm import Session
from app.models import Beer


THRESHOLD = 90  # juster senere (85-95)


def find_best_match(db: Session, normalized_name: str, volume_cl: float | None):
    candidates = db.query(Beer).all()

    best_score = 0
    best_match = None

    for beer in candidates:
        # volume skal matche nogenlunde
        if volume_cl and beer.volume_cl:
            if abs(beer.volume_cl - volume_cl) > 5:
                continue

        score = fuzz.token_sort_ratio(normalized_name, beer.normalized_name)

        if score > best_score:
            best_score = score
            best_match = beer

    if best_score >= THRESHOLD:
        return best_match

    return None