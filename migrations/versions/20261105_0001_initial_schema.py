"""Initial schema: settings, checkout sessions, orders (+items/events), visits and the delivery outbox.

Revision ID: 0001
Revises:
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('checkout_sessions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('items', sa.JSON(), nullable=False),
    sa.Column('subtotal', sa.BigInteger(), nullable=False),
    sa.Column('shipping', sa.BigInteger(), nullable=False),
    sa.Column('tax', sa.BigInteger(), nullable=False),
    sa.Column('total', sa.BigInteger(), nullable=False),
    sa.Column('customer_name', sa.String(length=200), nullable=False),
    sa.Column('customer_email', sa.String(length=200), nullable=False),
    sa.Column('customer_phone', sa.String(length=40), nullable=False),
    sa.Column('success_url', sa.Text(), nullable=False),
    sa.Column('cancel_url', sa.Text(), nullable=False),
    sa.Column('external_ref', sa.String(length=200), nullable=False),
    sa.Column('metadata', sa.JSON(), nullable=False),
    sa.Column('order_id', sa.String(length=40), nullable=True),
    sa.Column('viewed_at', mysql.DATETIME(fsp=3), nullable=True),
    sa.Column('created_at', mysql.DATETIME(fsp=3), nullable=False),
    sa.Column('expires_at', mysql.DATETIME(fsp=3), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_checkout_sessions'))
    )
    op.create_index('ix_checkout_sessions_created_at', 'checkout_sessions', ['created_at'], unique=False)
    op.create_index('ix_checkout_sessions_status_expires_at', 'checkout_sessions', ['status', 'expires_at'], unique=False)
    op.create_table('email_log',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('created_at', mysql.DATETIME(fsp=3), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('order_number', sa.BigInteger(), nullable=False),
    sa.Column('to_addr', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=500), nullable=False),
    sa.Column('body', sa.Text().with_variant(mysql.MEDIUMTEXT(), 'mysql'), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', mysql.DATETIME(fsp=3), nullable=True),
    sa.Column('sent_at', mysql.DATETIME(fsp=3), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_log'))
    )
    op.create_index('ix_email_log_created_at', 'email_log', ['created_at'], unique=False)
    op.create_index('ix_email_log_status_next_attempt_at', 'email_log', ['status', 'next_attempt_at'], unique=False)
    op.create_table('orders',
    sa.Column('number', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('public_id', sa.String(length=40), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('external_ref', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('payment_status', sa.String(length=16), nullable=False),
    sa.Column('payment_method_id', sa.String(length=40), nullable=False),
    sa.Column('payment_method_label', sa.String(length=80), nullable=False),
    sa.Column('payment_instructions', sa.Text(), nullable=False),
    sa.Column('payment_reference', sa.String(length=200), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('subtotal', sa.BigInteger(), nullable=False),
    sa.Column('shipping', sa.BigInteger(), nullable=False),
    sa.Column('tax', sa.BigInteger(), nullable=False),
    sa.Column('total', sa.BigInteger(), nullable=False),
    sa.Column('customer_name', sa.String(length=200), nullable=False),
    sa.Column('customer_email', sa.String(length=200), nullable=False),
    sa.Column('customer_phone', sa.String(length=40), nullable=False),
    sa.Column('ship_line1', sa.String(length=200), nullable=False),
    sa.Column('ship_line2', sa.String(length=200), nullable=False),
    sa.Column('ship_city', sa.String(length=100), nullable=False),
    sa.Column('ship_state', sa.String(length=100), nullable=False),
    sa.Column('ship_postal_code', sa.String(length=20), nullable=False),
    sa.Column('ship_country', sa.String(length=100), nullable=False),
    sa.Column('tracking_number', sa.String(length=200), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('metadata', sa.JSON(), nullable=False),
    sa.Column('paid_at', mysql.DATETIME(fsp=3), nullable=True),
    sa.Column('created_at', mysql.DATETIME(fsp=3), nullable=False),
    sa.Column('updated_at', mysql.DATETIME(fsp=3), nullable=False),
    sa.PrimaryKeyConstraint('number', name=op.f('pk_orders')),
    sa.UniqueConstraint('public_id', name=op.f('uq_orders_public_id')),
    sa.UniqueConstraint('session_id', name=op.f('uq_orders_session_id')),
    mysql_auto_increment='1001'
    )
    op.create_index('ix_orders_created_at', 'orders', ['created_at'], unique=False)
    op.create_index('ix_orders_external_ref', 'orders', ['external_ref'], unique=False)
    op.create_index('ix_orders_paid_at', 'orders', ['paid_at'], unique=False)
    op.create_index('ix_orders_payment_status', 'orders', ['payment_status'], unique=False)
    op.create_index('ix_orders_status', 'orders', ['status'], unique=False)
    op.create_table('settings',
    sa.Column('k', sa.String(length=64), nullable=False),
    sa.Column('v', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('k', name=op.f('pk_settings'))
    )
    op.create_table('visits',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('at', mysql.DATETIME(fsp=3), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('visitor', sa.String(length=12), nullable=False),
    sa.Column('device', sa.String(length=10), nullable=False),
    sa.Column('referrer', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_visits'))
    )
    op.create_index('ix_visits_at', 'visits', ['at'], unique=False)
    op.create_index('ix_visits_dedupe', 'visits', ['session_id', 'visitor', 'at'], unique=False)
    op.create_table('webhook_deliveries',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('created_at', mysql.DATETIME(fsp=3), nullable=False),
    sa.Column('event', sa.String(length=40), nullable=False),
    sa.Column('order_number', sa.BigInteger(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('payload', sa.Text().with_variant(mysql.MEDIUMTEXT(), 'mysql'), nullable=False),
    sa.Column('signature', sa.String(length=80), nullable=False),
    sa.Column('state', sa.String(length=10), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', mysql.DATETIME(fsp=3), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_deliveries'))
    )
    op.create_index('ix_webhook_deliveries_created_at', 'webhook_deliveries', ['created_at'], unique=False)
    op.create_index('ix_webhook_deliveries_state_next_attempt_at', 'webhook_deliveries', ['state', 'next_attempt_at'], unique=False)
    op.create_table('order_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('order_number', sa.BigInteger(), nullable=False),
    sa.Column('at', mysql.DATETIME(fsp=3), nullable=False),
    sa.Column('text', sa.String(length=500), nullable=False),
    sa.ForeignKeyConstraint(['order_number'], ['orders.number'], name=op.f('fk_order_events_order_number_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_events'))
    )
    op.create_index(op.f('ix_order_events_order_number'), 'order_events', ['order_number'], unique=False)
    op.create_table('order_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('order_number', sa.BigInteger(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('sku', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=False),
    sa.Column('image', sa.Text(), nullable=False),
    sa.Column('unit_amount', sa.BigInteger(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['order_number'], ['orders.number'], name=op.f('fk_order_items_order_number_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_order_items'))
    )
    op.create_index(op.f('ix_order_items_order_number'), 'order_items', ['order_number'], unique=False)


def downgrade() -> None:
    # Dropping a table drops its indexes; children are dropped before the orders table they reference.
    op.drop_table('order_items')
    op.drop_table('order_events')
    op.drop_table('webhook_deliveries')
    op.drop_table('visits')
    op.drop_table('settings')
    op.drop_table('orders')
    op.drop_table('email_log')
    op.drop_table('checkout_sessions')
