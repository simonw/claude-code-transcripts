"""Tests for database models."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from claude_code_transcripts.models import Base, Conversation


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_conversation_model_creation(db_session):
    """Test creating a Conversation model instance."""
    conversation = Conversation(
        session_id="test_session_123",
        source="web",
        last_updated=datetime(2025, 1, 1, 12, 0, 0),
        message_count=10,
        html_path="/path/to/html/test_session_123",
        first_message="Test conversation",
    )

    db_session.add(conversation)
    db_session.commit()

    # Retrieve and verify
    retrieved = (
        db_session.query(Conversation).filter_by(session_id="test_session_123").first()
    )
    assert retrieved is not None
    assert retrieved.session_id == "test_session_123"
    assert retrieved.source == "web"
    assert retrieved.message_count == 10
    assert retrieved.html_path == "/path/to/html/test_session_123"
    assert retrieved.first_message == "Test conversation"


def test_conversation_model_timestamps(db_session):
    """Test that created_at is automatically set."""
    conversation = Conversation(
        session_id="test_session_456",
        source="local",
        last_updated=datetime.now(),
        message_count=5,
        html_path="/path/to/html",
    )

    db_session.add(conversation)
    db_session.commit()

    retrieved = (
        db_session.query(Conversation).filter_by(session_id="test_session_456").first()
    )
    assert retrieved.created_at is not None
    assert isinstance(retrieved.created_at, datetime)


def test_conversation_model_unique_session_id(db_session):
    """Test that session_id must be unique."""
    conversation1 = Conversation(
        session_id="duplicate_id",
        source="web",
        last_updated=datetime.now(),
        message_count=1,
        html_path="/path1",
    )
    conversation2 = Conversation(
        session_id="duplicate_id",
        source="local",
        last_updated=datetime.now(),
        message_count=2,
        html_path="/path2",
    )

    db_session.add(conversation1)
    db_session.commit()

    db_session.add(conversation2)
    with pytest.raises(Exception):  # SQLAlchemy will raise an IntegrityError
        db_session.commit()
