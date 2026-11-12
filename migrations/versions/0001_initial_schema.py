"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-11 15:10:25.181763
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import pgvector.sqlalchemy.vector

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (% rejected)', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

APPEND_ONLY_TRIGGER = """
CREATE TRIGGER audit_events_no_update_delete
BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events
FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only();
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('audit_events',
    sa.Column('seq', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('subject_type', sa.String(length=40), nullable=False),
    sa.Column('subject_id', sa.String(length=80), nullable=False),
    sa.Column('request_id', sa.String(length=80), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('seq', name=op.f('pk_audit_events'))
    )
    op.create_index(op.f('ix_audit_events_action'), 'audit_events', ['action'], unique=False)
    op.create_index(op.f('ix_audit_events_actor_id'), 'audit_events', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_events_occurred_at'), 'audit_events', ['occurred_at'], unique=False)
    op.create_index(op.f('ix_audit_events_subject_id'), 'audit_events', ['subject_id'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=120), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents'))
    )
    op.create_table('past_projects',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('sector', sa.String(length=80), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('actual_hours', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=256), nullable=False),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_past_projects'))
    )
    op.create_table('rate_card',
    sa.Column('role', sa.String(length=60), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('cost_rate', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('sell_rate', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('role', name=op.f('pk_rate_card'))
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('failed_login_count', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('external_subject', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('viewer','estimator','approver','admin')", name=op.f('ck_users_role')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('external_subject', name=op.f('uq_users_external_subject'))
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_table('case_studies',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=256), nullable=False),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['past_projects.id'], name=op.f('fk_case_studies_project_id_past_projects')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_studies'))
    )
    op.create_table('refresh_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('brief_document_id', sa.UUID(), nullable=False),
    sa.Column('brief_filename', sa.String(length=255), nullable=False),
    sa.Column('brief_text', sa.Text(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('current_step', sa.String(length=40), nullable=True),
    sa.Column('revision_count', sa.Integer(), nullable=False),
    sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('requirements', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('references', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('estimate', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('quote', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('resource_plan', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('proposal', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('proposal_document_id', sa.UUID(), nullable=True),
    sa.Column('is_final', sa.Boolean(), nullable=False),
    sa.Column('review_comment', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('queued','running','awaiting_approval','approved','failed')", name=op.f('ck_runs_status')),
    sa.ForeignKeyConstraint(['brief_document_id'], ['documents.id'], name=op.f('fk_runs_brief_document_id_documents')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_runs_created_by_users')),
    sa.ForeignKeyConstraint(['proposal_document_id'], ['documents.id'], name=op.f('fk_runs_proposal_document_id_documents')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_runs'))
    )
    op.create_index(op.f('ix_runs_created_by'), 'runs', ['created_by'], unique=False)
    op.create_index(op.f('ix_runs_status'), 'runs', ['status'], unique=False)
    op.create_table('team_members',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.String(length=60), nullable=False),
    sa.Column('weekly_hours', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['role'], ['rate_card.role'], name=op.f('fk_team_members_role_rate_card')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_team_members'))
    )
    op.create_table('approvals',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('decision', sa.String(length=20), nullable=False),
    sa.Column('decided_by', sa.UUID(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("decision IN ('approved','rejected')", name=op.f('ck_approvals_decision')),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name=op.f('fk_approvals_decided_by_users')),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_approvals_run_id_runs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_approvals'))
    )
    op.create_index(op.f('ix_approvals_run_id'), 'approvals', ['run_id'], unique=False)
    op.create_table('invoice_milestones',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('percentage', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('net', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('vat', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('gross', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('vat_rate', sa.Numeric(precision=6, scale=4), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_invoice_milestones_run_id_runs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoice_milestones')),
    sa.UniqueConstraint('run_id', 'sequence', name='uq_invoice_milestones_seq')
    )
    op.create_index(op.f('ix_invoice_milestones_run_id'), 'invoice_milestones', ['run_id'], unique=False)
    op.create_table('pipeline_records',
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('reference', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('value', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('margin', sa.Numeric(precision=6, scale=4), nullable=False),
    sa.Column('stage', sa.String(length=40), nullable=False),
    sa.Column('approved_by', sa.UUID(), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], name=op.f('fk_pipeline_records_approved_by_users')),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_pipeline_records_run_id_runs')),
    sa.PrimaryKeyConstraint('run_id', name=op.f('pk_pipeline_records')),
    sa.UniqueConstraint('reference', name=op.f('uq_pipeline_records_reference'))
    )
    op.create_table('run_steps',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('step', sa.String(length=40), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_run_steps_run_id_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_run_steps')),
    sa.UniqueConstraint('run_id', 'step', 'attempt', name='uq_run_steps_attempt')
    )
    op.create_index(op.f('ix_run_steps_run_id'), 'run_steps', ['run_id'], unique=False)

    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(APPEND_ONLY_TRIGGER)

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")
    op.drop_index(op.f('ix_run_steps_run_id'), table_name='run_steps')
    op.drop_table('run_steps')
    op.drop_table('pipeline_records')
    op.drop_index(op.f('ix_invoice_milestones_run_id'), table_name='invoice_milestones')
    op.drop_table('invoice_milestones')
    op.drop_index(op.f('ix_approvals_run_id'), table_name='approvals')
    op.drop_table('approvals')
    op.drop_table('team_members')
    op.drop_index(op.f('ix_runs_status'), table_name='runs')
    op.drop_index(op.f('ix_runs_created_by'), table_name='runs')
    op.drop_table('runs')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_table('case_studies')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('rate_card')
    op.drop_table('past_projects')
    op.drop_table('documents')
    op.drop_index(op.f('ix_audit_events_subject_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_occurred_at'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_actor_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_action'), table_name='audit_events')
    op.drop_table('audit_events')
