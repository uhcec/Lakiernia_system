"""Enforce profile/accessory quantity sum

Revision ID: 20260531_0024
Revises: 20260531_0023
Create Date: 2026-05-31 22:15:00
"""

from alembic import op


revision = "20260531_0024"
down_revision = "20260531_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE work_orders
        SET profiles_quantity = NULL,
            profiles_to_count = 1,
            accessories_quantity = NULL,
            accessories_to_count = 1
        WHERE profiles_quantity IS NOT NULL
          AND accessories_quantity IS NOT NULL
          AND profiles_quantity + accessories_quantity != total_quantity
        """
    )

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_profiles_quantity_matches_total_if_known", type_="check")
        batch_op.drop_constraint("ck_work_orders_accessories_quantity_matches_total_if_known", type_="check")
        batch_op.create_check_constraint(
            "ck_work_orders_profiles_quantity_within_total_if_known",
            "profiles_quantity IS NULL OR (profiles_quantity >= 0 AND profiles_quantity <= total_quantity)",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_accessories_quantity_within_total_if_known",
            "accessories_quantity IS NULL OR (accessories_quantity >= 0 AND accessories_quantity <= total_quantity)",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_profile_accessory_quantities_sum_total_if_known",
            "profiles_quantity IS NULL OR accessories_quantity IS NULL OR profiles_quantity + accessories_quantity = total_quantity",
        )


def downgrade() -> None:
    op.execute(
        """
        UPDATE work_orders
        SET profiles_quantity = total_quantity
        WHERE profiles_quantity IS NOT NULL
          AND profiles_quantity > 0
          AND profiles_quantity != total_quantity
        """
    )
    op.execute(
        """
        UPDATE work_orders
        SET accessories_quantity = total_quantity
        WHERE accessories_quantity IS NOT NULL
          AND accessories_quantity > 0
          AND accessories_quantity != total_quantity
        """
    )

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_profiles_quantity_within_total_if_known", type_="check")
        batch_op.drop_constraint("ck_work_orders_accessories_quantity_within_total_if_known", type_="check")
        batch_op.drop_constraint("ck_work_orders_profile_accessory_quantities_sum_total_if_known", type_="check")
        batch_op.create_check_constraint(
            "ck_work_orders_profiles_quantity_matches_total_if_known",
            "profiles_quantity IS NULL OR profiles_quantity = 0 OR profiles_quantity = total_quantity",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_accessories_quantity_matches_total_if_known",
            "accessories_quantity IS NULL OR accessories_quantity = 0 OR accessories_quantity = total_quantity",
        )
