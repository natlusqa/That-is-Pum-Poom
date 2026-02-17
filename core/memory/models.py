"""
KORGAN AI — Database Models (SQLAlchemy)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interface = Column(String(50), nullable=False)  # telegram, desktop, voice, api
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    ended_at = Column(DateTime(timezone=True), nullable=True)
    summary = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, default=dict)

    messages = relationship("Message", back_populates="conversation", lazy="selectin")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True
    )
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=True)
    tokens_used = Column(Integer, default=0)
    model_used = Column(String(100), nullable=True)
    interface = Column(String(50), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    metadata_ = Column("metadata", JSONB, default=dict)

    conversation = relationship("Conversation", back_populates="messages")


class Fact(Base):
    __tablename__ = "facts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(50), nullable=False)  # preference, project, decision, personal
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    source_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    metadata_ = Column("metadata", JSONB, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action = Column(String(255), nullable=False)
    agent = Column(String(100), nullable=True)
    details = Column(JSONB, default=dict)
    risk_level = Column(String(20), default="low")  # low, medium, high, critical
    autonomy_level = Column(String(50), nullable=True)
    approved_by = Column(String(50), nullable=True)  # user, auto, conditional
    rollback_data = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name = Column(String(100), nullable=False)
    action_type = Column(String(100), nullable=False)
    input_data = Column(JSONB, default=dict)
    output_data = Column(JSONB, default=dict)
    status = Column(String(20), default="pending")  # pending, running, success, failed, rolled_back
    duration_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    metadata_ = Column("metadata", JSONB, default=dict)
