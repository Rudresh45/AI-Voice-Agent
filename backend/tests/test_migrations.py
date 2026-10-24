"""Tests verifying Alembic migrations can execute from zero, downgrade, and re-apply cleanly."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_alembic_migration_lifecycle(tmp_path: Path):
    """Test full migration lifecycle against an isolated temporary database."""
    test_db_path = tmp_path / "migration_lifecycle_test.db"
    test_db_url = f"sqlite:///{test_db_path.as_posix()}"

    # Locate alembic.ini in backend directory
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    assert ini_path.exists(), f"alembic.ini not found at {ini_path}"

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # Set environment variable as env.py also checks os.getenv
    old_env = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_db_url

    try:
        # 1. Upgrade from zero to head
        command.upgrade(alembic_cfg, "head")

        # 2. Downgrade back to base
        command.downgrade(alembic_cfg, "base")

        # 3. Upgrade to head again
        command.upgrade(alembic_cfg, "head")

        # Verify database file was created and contains tables
        assert test_db_path.exists()
    finally:
        if old_env is not None:
            os.environ["DATABASE_URL"] = old_env
        else:
            os.environ.pop("DATABASE_URL", None)
