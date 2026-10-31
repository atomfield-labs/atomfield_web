"""
SQLAlchemy ORM models for script releases: published versions of the
domain pack (afscripts), each with its catalog and its wheels.
"""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.catalog.models import WORKFLOW_ID_LENGTH
from app.core.machines import MACHINE_LENGTH
from app.core.names import version_label
from app.db.base import Base


class ScriptRelease(Base):
    """
    One published version of the scripts. Never changed afterwards: a
    change is a new release, so a run pinned to this one always gets
    exactly this code and this catalog.
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
    # Fingerprint of what was published, to spot other contents under
    # the same version.
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
        return version_label(self.name, self.version)


class ReleaseWheel(Base):
    """
    One file of a release: a package built for one kind of machine. The
    file itself is in the file store, under its fingerprint
    (``app.storage.keys``), which agents check after downloading.
    """

    __tablename__ = "release_wheels"

    release_id = Column(
        UUID(as_uuid=True),
        ForeignKey("script_releases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    package = Column(String(WORKFLOW_ID_LENGTH), primary_key=True)
    machine = Column(String(MACHINE_LENGTH), primary_key=True)
    sha256 = Column(String(64), nullable=False)
