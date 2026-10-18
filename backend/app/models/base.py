import uuid
import hashlib
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, Boolean, Numeric, Date, Enum, Table, UniqueConstraint, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


metadata = Base.metadata


def field(name, kind=Text, *, required=False, default=None, unique=False):
    return Column(name, kind, nullable=not required, server_default=default, unique=unique)


def ref(name, target, *, required=True, unique=False):
    return Column(name, UUID(as_uuid=True), ForeignKey(target, ondelete="RESTRICT"), nullable=not required, unique=unique)


def choice(name, values, *, required=True, default=None):
    signature = hashlib.sha256(values.encode()).hexdigest()[:10]
    return field(name, Enum(*values.split(), name=f"enum_{name}_{signature}"), required=required, default=default)


def table(name, *columns, constraints=()):
    return Table(name, metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
        *columns, *constraints)


def texts(names):
    return [field(name) for name in names.split()]


def lists(names):
    return [field(name, ARRAY(Text), required=True, default="{}") for name in names.split()]


def objects(names):
    return [field(name, JSONB, required=True, default="{}") for name in names.split()]


def dates(names):
    return [field(name, Date) for name in names.split()]


def ordered():
    return field("sort_order", Integer, required=True, default="0")
