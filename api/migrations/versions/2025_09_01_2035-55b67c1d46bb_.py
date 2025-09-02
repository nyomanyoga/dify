"""empty message

Revision ID: 55b67c1d46bb
Revises: 8d289573e1da, b45e25c2d166
Create Date: 2025-09-01 20:35:56.892375

"""
from alembic import op
import models as models
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '55b67c1d46bb'
down_revision = ('8d289573e1da', 'b45e25c2d166')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
