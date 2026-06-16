import os
import tempfile

import pytest


os.environ.setdefault("CAREWISE_ENV", "test")
os.environ.setdefault("CAREWISE_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CAREWISE_JWT_SECRET", "test-secret-that-is-long-enough")
os.environ.setdefault("CAREWISE_FIELD_ENCRYPTION_KEY", "test-fernet-key-for-carewise-tests")
os.environ.setdefault("CAREWISE_LOCAL_STORAGE_DIR", tempfile.mkdtemp(prefix="carewise-test-storage-"))
os.environ.setdefault("CAREWISE_ALLOWED_ORIGINS", "http://localhost:4173")

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.models import carewise  # noqa: E402,F401


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
