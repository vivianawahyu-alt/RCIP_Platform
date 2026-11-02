from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.shared.config import settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def run_migrations_online() -> None:
    engine = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None, include_schemas=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
