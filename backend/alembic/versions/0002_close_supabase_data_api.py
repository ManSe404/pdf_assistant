"""Keep the tables out of Supabase's Data API.

Supabase serves every table in the ``public`` schema over its REST and GraphQL APIs to
the ``anon`` and ``authenticated`` roles, which anyone with the project's publishable key
can use. pdf_assistant reads its tables only through its own backend, so on Supabase the
tables get row level security with no policies and those roles lose their grants. The
backend connects as the tables' owner, which row level security does not restrict.

Only runs where those roles exist (Supabase); SQLite and plain Postgres are left alone. A
table added later needs the same two statements.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 23:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("users", "pdfs", "conversations", "messages", "votes")
API_ROLES = ("anon", "authenticated")


def _is_supabase() -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    found = bind.execute(
        sa.text("SELECT count(*) FROM pg_roles WHERE rolname = ANY(:roles)"), {"roles": list(API_ROLES)}
    )
    return found.scalar_one() == len(API_ROLES)


def upgrade() -> None:
    if not _is_supabase():
        return
    roles = ", ".join(API_ROLES)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE {table} FROM {roles}")


def downgrade() -> None:
    if not _is_supabase():
        return
    roles = ", ".join(API_ROLES)
    for table in TABLES:
        op.execute(f"GRANT ALL ON TABLE {table} TO {roles}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
