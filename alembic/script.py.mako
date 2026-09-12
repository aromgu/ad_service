"""${context.get('message', 'init db')}

Revision ID: ${context.get('revision', 'unknown')}
Revises: ${context.get('down_revision', None)}
Create Date: ${context.get('create_date', '')}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${context.get('imports', '')}

# revision identifiers, used by Alembic.
revision: str = ${repr(context.get('revision', ''))}
down_revision: Union[str, None] = ${repr(context.get('down_revision', None))}
branch_labels: Union[str, Sequence[str], None] = ${repr(context.get('branch_labels', None))}
depends_on: Union[str, Sequence[str], None] = ${repr(context.get('depends_on', None))}


def upgrade() -> None:
    ${context.get('upgrades', 'pass')}


def downgrade() -> None:
    ${context.get('downgrades', 'pass')}