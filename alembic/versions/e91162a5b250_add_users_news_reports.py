"""add users news reports

Revision ID: e91162a5b250
Revises: bd27759d9c60
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e91162a5b250"
down_revision: Union[str, Sequence[str], None] = "bd27759d9c60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.String(length=100), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_users_id"), "users", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_users_telegram_id"),
        "users",
        ["telegram_id"],
        unique=True,
    )

    op.create_table(
        "news",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_news_company_id"),
        "news",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_news_id"), "news", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_news_published_at"),
        "news",
        ["published_at"],
        unique=False,
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reports_company_id"),
        "reports",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reports_id"),
        "reports",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_reports_id"),
        table_name="reports",
    )
    op.drop_index(
        op.f("ix_reports_company_id"),
        table_name="reports",
    )
    op.drop_table("reports")

    op.drop_index(
        op.f("ix_news_published_at"),
        table_name="news",
    )
    op.drop_index(
        op.f("ix_news_id"),
        table_name="news",
    )
    op.drop_index(
        op.f("ix_news_company_id"),
        table_name="news",
    )
    op.drop_table("news")

    op.drop_index(
        op.f("ix_users_telegram_id"),
        table_name="users",
    )
    op.drop_index(
        op.f("ix_users_id"),
        table_name="users",
    )
    op.drop_table("users")
