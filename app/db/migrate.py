from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import settings


def alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def migrate_database() -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    has_existing_schema = "users" in table_names and "patient_profiles" in table_names
    has_alembic_version = "alembic_version" in table_names

    config = alembic_config()
    if has_existing_schema and not has_alembic_version:
        command.stamp(config, "head")
    command.upgrade(config, "head")


if __name__ == "__main__":
    migrate_database()
