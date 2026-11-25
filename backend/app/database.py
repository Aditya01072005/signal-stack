from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Create reusable synchronous engine connected via psycopg
engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,  # Proactively test connection freshness before checkout
    pool_recycle=300,   # Recycle connections after 5 minutes to play nicely with serverless poolers
)

# Reusable session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
