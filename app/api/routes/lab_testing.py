from fastapi import APIRouter, HTTPException, status

from app.services.lab_testing import LIVE
from app.services.lab_testing.catalog import CATEGORIES, catalog

# Read-only. The catalog is synthetic and every test is unavailable until a lab partner,
# an ordering arrangement and legal review are in place. No ordering endpoint exists yet.
router = APIRouter()


@router.get("/catalog")
def lab_catalog(category: str | None = None):
    if category and category not in {item.key for item in CATEGORIES}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such category.")
    return {
        "live": LIVE,
        "synthetic": True,
        "notice": "Lab testing is planned, not available yet. Tests, prices and locations will come from signed lab partners.",
        "categories": catalog(category),
    }
