"""Add the soft-delete flag required by the job deletion contract."""
from alembic import op
import sqlalchemy as sa
revision='0002_job_soft_delete'
down_revision='0001_foundation'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('job',sa.Column('is_deleted',sa.Boolean(),nullable=False,server_default=sa.false()))


def downgrade():
    op.drop_column('job','is_deleted')
