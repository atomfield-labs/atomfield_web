"""
SQLAlchemy ORM model for script releases: published versions of the
domain pack (afscripts), each with the catalog it carries.
"""

import uuid

from sqlalchemy import Column, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class ScriptRelease(Base):
    """
    One published version of the scripts. Never changed afterwards: a
    change is a new release, so a run pinned to this one always gets
    exactly this code and this catalog. The wheel itself is in the
    file store, under its fingerprint (``app.storage.keys``).
    """

    __tablename__ = "script_releases"
    __table_args__ = (
        UniqueConstraint(
            "name", "version", name="uq_script_releases_name_version"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    version = Column(String(100), nullable=False)
    # Fingerprint of the wheel; agents check it after downloading.
    sha256 = Column(String(64), nullable=False)
    # The git commit it was built from, as the publisher reported it.
    git_commit = Column(String(40), nullable=True)
    catalog = Column(JSONB, nullable=False)
    published_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    @property
    def label(self) -> str:
        """
        How people see it: ``afscripts 0.2.0+g2e6d386``.

        :return: Name and version.
        :rtype: str
        """
        return f"{self.name} {self.version}"
