"""reference gallery unified taxonomies

Revision ID: 202606250001
Revises: 202606220001
Create Date: 2026-06-25 00:00:01.000000

"""
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "202606250001"
down_revision: Union[str, Sequence[str], None] = "202606220001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> Any:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _column_nullable(table_name: str, column_name: str) -> bool:
    for column in _inspector().get_columns(table_name):
        if column["name"] == column_name:
            return bool(column.get("nullable", True))
    return True


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _unique_exists(table_name: str, constraint_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(
        constraint["name"] == constraint_name
        for constraint in _inspector().get_unique_constraints(table_name)
    )


def _check_exists(table_name: str, constraint_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    try:
        return any(
            constraint["name"] == constraint_name
            for constraint in _inspector().get_check_constraints(table_name)
        )
    except NotImplementedError:
        return False


def _foreign_key_names(table_name: str, columns: Sequence[str]) -> list[str]:
    if not _table_exists(table_name):
        return []
    expected = set(columns)
    return [
        foreign_key["name"]
        for foreign_key in _inspector().get_foreign_keys(table_name)
        if set(foreign_key.get("constrained_columns") or []) == expected
        and foreign_key.get("name")
    ]


def _foreign_key_exists(table_name: str, columns: Sequence[str], referred_table: str) -> bool:
    if not _table_exists(table_name):
        return False
    expected = set(columns)
    return any(
        set(foreign_key.get("constrained_columns") or []) == expected
        and foreign_key.get("referred_table") == referred_table
        for foreign_key in _inspector().get_foreign_keys(table_name)
    )


def upgrade() -> None:
    if _table_exists("reference_categories") and not _table_exists("reference_taxonomies"):
        op.rename_table("reference_categories", "reference_taxonomies")

    taxonomy_columns = _column_names("reference_taxonomies")
    with op.batch_alter_table("reference_taxonomies") as batch:
        if _unique_exists("reference_taxonomies", "uq_reference_categories_name"):
            batch.drop_constraint("uq_reference_categories_name", type_="unique")
        if "kind" not in taxonomy_columns:
            batch.add_column(sa.Column("kind", sa.String(length=32), nullable=True))
        if "prompt" not in taxonomy_columns:
            batch.add_column(sa.Column("prompt", sa.Text(), nullable=True))
        if not _unique_exists("reference_taxonomies", "uq_reference_taxonomies_kind_name"):
            batch.create_unique_constraint("uq_reference_taxonomies_kind_name", ["kind", "name"])
        if not _check_exists("reference_taxonomies", "ck_reference_taxonomies_kind"):
            batch.create_check_constraint(
                "ck_reference_taxonomies_kind",
                "kind IN ('category', 'style', 'classification')",
            )
        if not _index_exists("reference_taxonomies", "ix_reference_taxonomies_kind"):
            batch.create_index("ix_reference_taxonomies_kind", ["kind"], unique=False)

    op.execute("UPDATE reference_taxonomies SET kind = 'category' WHERE kind IS NULL")

    if _column_nullable("reference_taxonomies", "kind"):
        with op.batch_alter_table("reference_taxonomies") as batch:
            batch.alter_column("kind", existing_type=sa.String(length=32), nullable=False)

    image_columns = _column_names("reference_images")
    with op.batch_alter_table("reference_images") as batch:
        if "category_id" not in image_columns:
            batch.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        if "style_id" not in image_columns:
            batch.add_column(sa.Column("style_id", sa.Integer(), nullable=True))
        if "classification_id" not in image_columns:
            batch.add_column(sa.Column("classification_id", sa.Integer(), nullable=True))

    image_columns = _column_names("reference_images")
    if "category_id" in image_columns and "subcategory_id" in image_columns and _table_exists("reference_subcategories"):
        op.execute(
            """
            UPDATE reference_images
            SET category_id = (
                SELECT reference_subcategories.category_id
                FROM reference_subcategories
                WHERE reference_subcategories.id = reference_images.subcategory_id
            )
            WHERE category_id IS NULL
            """
        )

    image_columns = _column_names("reference_images")
    subcategory_fk_names = _foreign_key_names("reference_images", ["subcategory_id"])
    with op.batch_alter_table("reference_images") as batch:
        for foreign_key_name in subcategory_fk_names:
            batch.drop_constraint(foreign_key_name, type_="foreignkey")
        if _index_exists("reference_images", "ix_reference_images_subcategory_id"):
            batch.drop_index("ix_reference_images_subcategory_id")
        if "subcategory_id" in image_columns:
            batch.drop_column("subcategory_id")
        if "category_id" in image_columns and _column_nullable("reference_images", "category_id"):
            batch.alter_column("category_id", existing_type=sa.Integer(), nullable=False)
        if not _foreign_key_exists("reference_images", ["category_id"], "reference_taxonomies"):
            batch.create_foreign_key(
                "fk_reference_images_category_id_reference_taxonomies",
                "reference_taxonomies",
                ["category_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if not _foreign_key_exists("reference_images", ["style_id"], "reference_taxonomies"):
            batch.create_foreign_key(
                "fk_reference_images_style_id_reference_taxonomies",
                "reference_taxonomies",
                ["style_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if not _foreign_key_exists("reference_images", ["classification_id"], "reference_taxonomies"):
            batch.create_foreign_key(
                "fk_reference_images_classification_id_reference_taxonomies",
                "reference_taxonomies",
                ["classification_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if not _index_exists("reference_images", "ix_reference_images_category_id"):
            batch.create_index("ix_reference_images_category_id", ["category_id"], unique=False)
        if not _index_exists("reference_images", "ix_reference_images_style_id"):
            batch.create_index("ix_reference_images_style_id", ["style_id"], unique=False)
        if not _index_exists("reference_images", "ix_reference_images_classification_id"):
            batch.create_index(
                "ix_reference_images_classification_id",
                ["classification_id"],
                unique=False,
            )

    if _table_exists("reference_subcategories"):
        op.drop_table("reference_subcategories")


def downgrade() -> None:
    op.create_table(
        "reference_subcategories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["category_id"], ["reference_taxonomies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "name", name="uq_reference_subcategories_category_name"),
    )
    op.create_index("ix_reference_subcategories_created_by", "reference_subcategories", ["created_by"])
    op.create_index(
        "ix_reference_subcategories_category_id",
        "reference_subcategories",
        ["category_id"],
    )

    op.execute(
        """
        INSERT INTO reference_subcategories (category_id, created_by, name)
        SELECT id, created_by, '默认'
        FROM reference_taxonomies
        WHERE kind = 'category'
        """
    )

    with op.batch_alter_table("reference_images") as batch:
        batch.add_column(sa.Column("subcategory_id", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE reference_images
        SET subcategory_id = (
            SELECT reference_subcategories.id
            FROM reference_subcategories
            WHERE reference_subcategories.category_id = reference_images.category_id
            LIMIT 1
        )
        WHERE subcategory_id IS NULL
        """
    )

    with op.batch_alter_table("reference_images") as batch:
        batch.drop_index("ix_reference_images_classification_id")
        batch.drop_index("ix_reference_images_style_id")
        batch.drop_index("ix_reference_images_category_id")
        batch.drop_column("classification_id")
        batch.drop_column("style_id")
        batch.drop_column("category_id")
        batch.alter_column("subcategory_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_reference_images_subcategory_id_reference_subcategories",
            "reference_subcategories",
            ["subcategory_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_reference_images_subcategory_id", ["subcategory_id"], unique=False)

    with op.batch_alter_table("reference_taxonomies") as batch:
        batch.drop_index("ix_reference_taxonomies_kind")
        batch.drop_constraint("ck_reference_taxonomies_kind", type_="check")
        batch.drop_constraint("uq_reference_taxonomies_kind_name", type_="unique")
        batch.drop_column("prompt")
        batch.drop_column("kind")
        batch.create_unique_constraint("uq_reference_categories_name", ["name"])

    op.rename_table("reference_taxonomies", "reference_categories")
