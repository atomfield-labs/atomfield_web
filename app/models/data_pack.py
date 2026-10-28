"""
SQLAlchemy ORM model for data packs: zip files of data that tasks read
(pseudopotentials, model weights), published once and never changed.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class DataPack(Base):
    """
    One published version of a data pack. A change is a new version,
    so a task naming this version always reads exactly these bytes.
    The zip itself is in the file store (``app.storage.keys``).
    """

    __tablename__ = "data_packs"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_data_packs_name_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    version = Column(String(100), nullable=False)
    # Fingerprint of the zip; agents check it after downloading.
    sha256 = Column(String(64), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    published_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
