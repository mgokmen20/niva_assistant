"""SQLAlchemy 2.0 declarative base shared by every ORM model."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Metadata registry for Niva tables."""
