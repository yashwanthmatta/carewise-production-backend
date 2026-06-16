from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models import carewise  # noqa: F401


def init_local_database() -> None:
    if settings.env not in {"local", "development", "test"}:
        return
    Base.metadata.create_all(bind=engine)
