from logging.config import fileConfig

from alembic import context
from pdf_assistant import models  # noqa: F401  (registers the tables)
from pdf_assistant.db import Base, make_engine
from pdf_assistant.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.sqlalchemy_url)
    with engine.connect() as connection:
        # Batch mode lets later migrations alter SQLite tables (copy and swap).
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
