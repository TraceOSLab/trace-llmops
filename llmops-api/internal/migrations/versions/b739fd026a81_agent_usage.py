"""保存 Agent 用量与费率快照，扩大 Decimal 精度。

Revision ID: b739fd026a81
Revises: 56cd44058b99
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b739fd026a81"
down_revision = "56cd44058b99"
branch_labels = None
depends_on = None

PRICE_COLUMNS = ("message_unit_price", "answer_unit_price", "total_price")
UNIT_COLUMNS = ("message_price_unit", "answer_price_unit")


def upgrade():
    for table in ("message", "message_agent_thought"):
        op.add_column(table, sa.Column("usage", postgresql.JSONB(), nullable=False,
                                      server_default=sa.text("'{}'::jsonb")))
        for column in PRICE_COLUMNS + UNIT_COLUMNS:
            op.alter_column(table, column, type_=sa.Numeric(18, 10),
                            existing_type=sa.Numeric(10, 4 if column in UNIT_COLUMNS else 7),
                            existing_nullable=False)


def downgrade():
    # 缩小精度可能丢失小数或溢出，仅在确认开发/测试库后执行。
    for table in ("message_agent_thought", "message"):
        for column in PRICE_COLUMNS + UNIT_COLUMNS:
            op.alter_column(table, column,
                            type_=sa.Numeric(10, 4 if column in UNIT_COLUMNS else 7),
                            existing_type=sa.Numeric(18, 10), existing_nullable=False)
        op.drop_column(table, "usage")
