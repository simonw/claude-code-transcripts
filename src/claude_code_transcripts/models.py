"""Database models for transcript metadata."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Conversation(Base):
    """Model for storing transcript metadata."""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    source = Column(String(50), nullable=False)  # 'web' or 'local'
    last_updated = Column(DateTime, nullable=False)
    message_count = Column(Integer, nullable=False)
    html_path = Column(String(512), nullable=False)
    first_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Conversation(session_id='{self.session_id}', source='{self.source}', messages={self.message_count})>"


def get_engine(database_url):
    """Create a database engine."""
    return create_engine(database_url)


def get_session(engine):
    """Create a database session."""
    Session = sessionmaker(bind=engine)
    return Session()


def init_db(database_url):
    """Initialize the database with all tables."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    return engine
