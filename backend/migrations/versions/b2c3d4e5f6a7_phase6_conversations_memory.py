"""phase6_conversations_memory

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-24 16:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | Sequence[str] | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update conversations table with batch_alter_table for SQLite compatibility
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.add_column(sa.Column('summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('retention_days', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('meta_data', sa.JSON(), nullable=False, server_default='{}'))

    # 2. Update messages table with idempotency_key
    with op.batch_alter_table('messages') as batch_op:
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=120), nullable=True))
        batch_op.create_index('ix_messages_tenant_idempotency', ['tenant_id', 'idempotency_key'], unique=False)

    # 3. Create memory_facts table
    op.create_table(
        'memory_facts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('agent_id', sa.Uuid(), nullable=True),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('fact', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False, server_default='fact'),
        sa.Column('is_approved', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('approved_by', sa.Uuid(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('retention_days', sa.Integer(), nullable=True),
        sa.Column('meta_data', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_memory_facts_tenant_approved', 'memory_facts', ['tenant_id', 'is_approved'], unique=False)
    op.create_index('ix_memory_facts_tenant_created', 'memory_facts', ['tenant_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_memory_facts_tenant_created', table_name='memory_facts')
    op.drop_index('ix_memory_facts_tenant_approved', table_name='memory_facts')
    op.drop_table('memory_facts')

    with op.batch_alter_table('messages') as batch_op:
        batch_op.drop_index('ix_messages_tenant_idempotency')
        batch_op.drop_column('idempotency_key')

    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_column('meta_data')
        batch_op.drop_column('archived_at')
        batch_op.drop_column('retention_days')
        batch_op.drop_column('summary')
