from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.models.base import Base


class Permission(Base):
    """Permission associated with an organization (namespaced per org)."""

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_permissions_org_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    roles = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
