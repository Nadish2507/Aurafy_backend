import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the backend directory is in the sys.path so Python can find 'app'
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Import settings and target metadata
from app.core.config import settings
from app.models import Base

# this is the Alembic Config object, which provides access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for autogenerate support
target_metadata = Base.metadata

# Dynamic database URL override from env settings
config.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URI)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    By skipping the Engine creation we don't even need a DB API to be installed.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
