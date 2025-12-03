from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from src.models.base import Base


class Organization(Base):
    """Organization represents a tenant."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("name", name="uq_organizations_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
