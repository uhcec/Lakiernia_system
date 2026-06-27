"""Add phase 1 core invariant check constraints

Revision ID: 20260527_0012
Revises: 20260527_0011
Create Date: 2026-05-27 00:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260527_0012"
down_revision = "20260527_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    _assert_no_dirty_work_orders(connection)
    _assert_no_dirty_batches(connection)
    _assert_no_dirty_stage_states(connection)

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_work_orders_total_quantity_positive",
            "total_quantity > 0",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_completed_quantity_non_negative",
            "completed_quantity >= 0",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_completed_quantity_lte_total_quantity",
            "completed_quantity <= total_quantity",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_queue_position_positive_if_present",
            "queue_position IS NULL OR queue_position >= 1",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_planned_requires_production_type_and_queue_position",
            "(production_type IS NULL AND queue_position IS NULL) OR (production_type IS NOT NULL AND queue_position IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_profiles_quantity_positive_if_present",
            "profiles_quantity IS NULL OR profiles_quantity > 0",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_accessories_quantity_positive_if_present",
            "accessories_quantity IS NULL OR accessories_quantity > 0",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_parent_order_cannot_reference_self",
            "parent_order_id IS NULL OR parent_order_id != id",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_correction_namespace_consistent",
            "(is_correction = 1 AND queue_namespace = 'CORRECTIONS') OR (is_correction = 0 AND queue_namespace = 'MAIN')",
        )

    with op.batch_alter_table("work_order_quantity_batches", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_work_order_quantity_batches_quantity_positive",
            "quantity > 0",
        )
        batch_op.create_check_constraint(
            "ck_work_order_quantity_batches_current_stage_and_status_nullness_match",
            "(current_stage IS NULL AND current_stage_status IS NULL) OR (current_stage IS NOT NULL AND current_stage_status IS NOT NULL)",
        )

    with op.batch_alter_table("work_order_stage_states", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_work_order_stage_states_counted_quantity_positive_if_present",
            "counted_quantity IS NULL OR counted_quantity > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("work_order_stage_states", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_order_stage_states_counted_quantity_positive_if_present", type_="check")

    with op.batch_alter_table("work_order_quantity_batches", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_order_quantity_batches_current_stage_and_status_nullness_match", type_="check")
        batch_op.drop_constraint("ck_work_order_quantity_batches_quantity_positive", type_="check")

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_correction_namespace_consistent", type_="check")
        batch_op.drop_constraint("ck_work_orders_parent_order_cannot_reference_self", type_="check")
        batch_op.drop_constraint("ck_work_orders_accessories_quantity_positive_if_present", type_="check")
        batch_op.drop_constraint("ck_work_orders_profiles_quantity_positive_if_present", type_="check")
        batch_op.drop_constraint(
            "ck_work_orders_planned_requires_production_type_and_queue_position",
            type_="check",
        )
        batch_op.drop_constraint("ck_work_orders_queue_position_positive_if_present", type_="check")
        batch_op.drop_constraint("ck_work_orders_completed_quantity_lte_total_quantity", type_="check")
        batch_op.drop_constraint("ck_work_orders_completed_quantity_non_negative", type_="check")
        batch_op.drop_constraint("ck_work_orders_total_quantity_positive", type_="check")


def _assert_no_dirty_work_orders(connection) -> None:
    _assert_clean(
        connection,
        "SELECT id FROM work_orders WHERE total_quantity <= 0 LIMIT 1",
        "work_orders.total_quantity > 0",
        "work_order_id",
    )
    _assert_clean(
        connection,
        "SELECT id FROM work_orders WHERE completed_quantity < 0 LIMIT 1",
        "work_orders.completed_quantity >= 0",
        "work_order_id",
    )
    _assert_clean(
        connection,
        "SELECT id FROM work_orders WHERE completed_quantity > total_quantity LIMIT 1",
        "work_orders.completed_quantity <= total_quantity",
        "work_order_id",
    )
    _assert_clean(
        connection,
        "SELECT id FROM work_orders WHERE queue_position IS NOT NULL AND queue_position < 1 LIMIT 1",
        "work_orders.queue_position IS NULL OR queue_position >= 1",
        "work_order_id",
    )
    _assert_clean(
        connection,
        """
        SELECT id
        FROM work_orders
        WHERE (production_type IS NULL AND queue_position IS NOT NULL)
           OR (production_type IS NOT NULL AND queue_position IS NULL)
        LIMIT 1
        """,
        "work_orders.production_type and queue_position must both be null or both be non-null",
        "work_order_id",
    )
    _assert_clean(
        connection,
        "SELECT id FROM work_orders WHERE profiles_quantity IS NOT NULL AND profiles_quantity <= 0 LIMIT 1",
        "work_orders.profiles_quantity IS NULL OR profiles_quantity > 0",
        "work_order_id",
    )
    _assert_clean(
        connection,
        "SELECT id FROM work_orders WHERE accessories_quantity IS NOT NULL AND accessories_quantity <= 0 LIMIT 1",
        "work_orders.accessories_quantity IS NULL OR accessories_quantity > 0",
        "work_order_id",
    )
    _assert_clean(
        connection,
        "SELECT id FROM work_orders WHERE parent_order_id = id LIMIT 1",
        "work_orders.parent_order_id IS NULL OR parent_order_id != id",
        "work_order_id",
    )
    _assert_clean(
        connection,
        """
        SELECT id
        FROM work_orders
        WHERE (is_correction = 1 AND queue_namespace != 'CORRECTIONS')
           OR (is_correction = 0 AND queue_namespace != 'MAIN')
        LIMIT 1
        """,
        "work_orders correction namespace consistency",
        "work_order_id",
    )


def _assert_no_dirty_batches(connection) -> None:
    _assert_clean(
        connection,
        "SELECT id FROM work_order_quantity_batches WHERE quantity <= 0 LIMIT 1",
        "work_order_quantity_batches.quantity > 0",
        "batch_id",
    )
    _assert_clean(
        connection,
        """
        SELECT id
        FROM work_order_quantity_batches
        WHERE (current_stage IS NULL AND current_stage_status IS NOT NULL)
           OR (current_stage IS NOT NULL AND current_stage_status IS NULL)
        LIMIT 1
        """,
        "work_order_quantity_batches current_stage/current_stage_status nullness parity",
        "batch_id",
    )


def _assert_no_dirty_stage_states(connection) -> None:
    _assert_clean(
        connection,
        "SELECT id FROM work_order_stage_states WHERE counted_quantity IS NOT NULL AND counted_quantity <= 0 LIMIT 1",
        "work_order_stage_states.counted_quantity IS NULL OR counted_quantity > 0",
        "stage_state_id",
    )


def _assert_clean(connection, query: str, invariant_label: str, id_label: str) -> None:
    row = connection.execute(sa.text(query)).fetchone()
    if row is None:
        return

    violating_id = row[0]
    raise RuntimeError(
        f"Cannot apply migration {revision}: dirty data violates {invariant_label}. "
        f"Example {id_label}={violating_id}. Clean the data before upgrading."
    )
