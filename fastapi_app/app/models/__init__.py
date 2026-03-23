# Import all models here so that Base.metadata is fully populated
# before Alembic or create_all() is called.
from app.models.user import User
from app.models.patent import Patent

__all__ = ["User", "Patent"]