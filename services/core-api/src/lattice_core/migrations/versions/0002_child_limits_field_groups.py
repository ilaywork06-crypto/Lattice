"""Child-template limits and catalog field groups.

* ``template_children`` gains ``min_count`` / ``max_count``: how many units of a
  child template one item of the parent template holds (existing rows keep "no
  limits": 0 .. unlimited).
* ``field_groups`` / ``field_group_fields``: named, reusable sets of field
  definitions that the template editor loads in one go.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIELD_TYPES = (
    'text', 'description', 'string', 'serial_string', 'link', 'enum', 'letter', 'date',
    'integer', 'decimal', 'boolean', 'files', 'industry', 'project', 'team', 'managers',
    'responsible', 'location', 'parent', 'status', 'quantity',
)


def upgrade() -> None:
    with op.batch_alter_table('template_children', schema=None) as batch_op:
        batch_op.add_column(sa.Column('min_count', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('max_count', sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            op.f('ck_template_children_min_count_non_negative'), 'min_count >= 0'
        )
        batch_op.create_check_constraint(
            op.f('ck_template_children_max_count_valid'),
            'max_count IS NULL OR (max_count >= 1 AND max_count >= min_count)',
        )

    op.create_table('field_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_field_groups_created_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_field_groups'))
    )
    with op.batch_alter_table('field_groups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_field_groups_name'), ['name'], unique=True)

    op.create_table('field_group_fields',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('field_type', sa.Enum(*_FIELD_TYPES, name='field_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('mode', sa.Enum('fixed', 'choice', 'item', name='field_mode', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('required', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('fixed_value', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['group_id'], ['field_groups.id'], name=op.f('fk_field_group_fields_group_id_field_groups'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_field_group_fields')),
    sa.UniqueConstraint('group_id', 'key', name='uq_field_group_fields_key')
    )
    with op.batch_alter_table('field_group_fields', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_field_group_fields_group_id'), ['group_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('field_group_fields', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_field_group_fields_group_id'))
    op.drop_table('field_group_fields')
    with op.batch_alter_table('field_groups', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_field_groups_name'))
    op.drop_table('field_groups')

    with op.batch_alter_table('template_children', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_template_children_max_count_valid'), type_='check')
        batch_op.drop_constraint(op.f('ck_template_children_min_count_non_negative'), type_='check')
        batch_op.drop_column('max_count')
        batch_op.drop_column('min_count')
