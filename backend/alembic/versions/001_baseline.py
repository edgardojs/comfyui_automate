"""Baseline migration — captures the full schema as of P1-4.

This migration represents the database schema at the point where Alembic
is adopted. It includes all tables and columns that existed before Alembic,
including the comfyui_prompt_id and comfyui_images columns that were
previously added via ad-hoc ALTER TABLE statements in init_db().

For existing databases, this migration will be a no-op (stamp only).
For new databases, init_db() still uses create_all() as a fallback,
and this migration serves as the authoritative schema definition.

Revision ID: 001_baseline
Revises:
Create Date: 2026-06-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- presets table ---
    op.create_table(
        'presets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('preset_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('attributes', sa.Text(), nullable=False),
        sa.Column('locked_fields', sa.Text(), nullable=False),
        sa.Column('positive_template_id', sa.String(), nullable=False, server_default='front_view_sprite'),
        sa.Column('negative_profile_id', sa.String(), nullable=False, server_default='general_sprite_cleanup'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('preset_id'),
    )
    op.create_index('ix_presets_preset_id', 'presets', ['preset_id'])

    # --- prompt_history table ---
    op.create_table(
        'prompt_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('generation_id', sa.String(), nullable=False),
        sa.Column('character_id', sa.String(), nullable=False),
        sa.Column('project_name', sa.String(), nullable=False),
        sa.Column('character_name', sa.String(), nullable=False),
        sa.Column('positive_prompt', sa.Text(), nullable=False),
        sa.Column('negative_prompt', sa.Text(), nullable=False),
        sa.Column('variation_count', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.String(), nullable=False, server_default='front_view_sprite'),
        sa.Column('negative_profile_id', sa.String(), nullable=False, server_default='general_sprite_cleanup'),
        sa.Column('attributes', sa.Text(), nullable=False),
        sa.Column('locked_fields', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        # Columns previously added via ALTER TABLE in init_db()
        sa.Column('comfyui_prompt_id', sa.String(), nullable=True),
        sa.Column('comfyui_images', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_prompt_history_generation_id', 'prompt_history', ['generation_id'])

    # --- character_profiles table ---
    op.create_table(
        'character_profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('character_id', sa.String(), nullable=False),
        sa.Column('project_name', sa.String(), nullable=False),
        sa.Column('character_name', sa.String(), nullable=False),
        sa.Column('trigger_token', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('attributes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_character_profiles_character_id', 'character_profiles', ['character_id'])

    # --- reference_images table ---
    op.create_table(
        'reference_images',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('image_id', sa.String(), nullable=False),
        sa.Column('character_id', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('original_filename', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('angle', sa.String(), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reference_images_image_id', 'reference_images', ['image_id'])

    # --- lora_jobs table ---
    op.create_table(
        'lora_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('character_id', sa.String(), nullable=False),
        sa.Column('project_name', sa.String(), nullable=False),
        sa.Column('character_name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('preset_id', sa.String(), nullable=True),
        sa.Column('base_model', sa.String(), nullable=True),
        sa.Column('learning_rate', sa.Float(), nullable=True),
        sa.Column('epochs', sa.Integer(), nullable=True),
        sa.Column('preview_interval', sa.Integer(), nullable=True),
        sa.Column('output_format', sa.String(), nullable=True),
        sa.Column('lora_strength', sa.Float(), nullable=True),
        sa.Column('custom_args', sa.Text(), nullable=True),
        sa.Column('output_lora_path', sa.String(), nullable=True),
        sa.Column('log_output', sa.Text(), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('training_backend', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lora_jobs_job_id', 'lora_jobs', ['job_id'])


def downgrade() -> None:
    op.drop_table('lora_jobs')
    op.drop_table('reference_images')
    op.drop_table('character_profiles')
    op.drop_table('prompt_history')
    op.drop_table('presets')