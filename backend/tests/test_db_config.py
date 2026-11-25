import os
from urllib.parse import urlparse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base


def get_test_db_url() -> str:
    """
    Retrieves and strictly validates TEST_DATABASE_URL against production DATABASE_URL.
    Raises RuntimeError if safety checks fail.
    """
    test_url = os.getenv("TEST_DATABASE_URL", "").strip()
    prod_url = settings.DATABASE_URL.strip()

    if not test_url:
        raise RuntimeError(
            "SAFETY CHECK FAILED: 'TEST_DATABASE_URL' is not configured.\n"
            "Automated tests are blocked from executing against the production database.\n"
            "Please configure an isolated PostgreSQL test database in PowerShell:\n"
            '  $env:TEST_DATABASE_URL="postgresql+psycopg://.../signal_stack_test?sslmode=require"'
        )

    # Convert to SQLAlchemy psycopg scheme if needed
    if test_url.startswith("postgres://"):
        test_url = test_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif test_url.startswith("postgresql://") and not test_url.startswith("postgresql+"):
        test_url = test_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Parse both URLs to inspect host and database path
    test_parsed = urlparse(test_url)
    prod_parsed = urlparse(prod_url)

    test_db_name = test_parsed.path.lstrip("/").split("?")[0].lower()
    prod_db_name = prod_parsed.path.lstrip("/").split("?")[0].lower()

    # Compare exact target database names and hosts
    if test_url == settings.sync_database_url or (
        test_parsed.hostname == prod_parsed.hostname and test_db_name == prod_db_name
    ):
        raise RuntimeError(
            f"SAFETY CHECK FAILED: TEST_DATABASE_URL points to the production database ('{prod_db_name}').\n"
            "Tests are strictly prohibited from targeting production.\n"
            "Target a separate test database (e.g. 'signal_stack_test') or a dedicated Neon test branch."
        )

    return test_url


def create_test_engine_and_session():
    """Initializes isolated test database engine, tables, and session factory."""
    test_url = get_test_db_url()

    test_engine = create_engine(
        test_url,
        pool_pre_ping=True,
        pool_recycle=300,
    )

    # Initialize all models in the isolated test database
    import app.models  # Ensures all models are registered with Base.metadata
    Base.metadata.create_all(bind=test_engine)

    # Ensure canonical index is active in test database
    with test_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("DROP INDEX IF EXISTS uq_companies_active_website_lower;"))
        conn.execute(text("DROP INDEX IF EXISTS uq_companies_active_website_canonical;"))
        conn.execute(text("""
            CREATE UNIQUE INDEX uq_companies_active_website_canonical ON companies (
                (
                    lower(substring(website_url from '^([a-zA-Z]+://[^/?#]+)')) ||
                    regexp_replace(
                        coalesce(substring(website_url from '^[a-zA-Z]+://[^/?#]+(.*)$'), ''),
                        '/+(?=[?#]|$)',
                        '',
                        'g'
                    )
                )
            ) WHERE is_deleted = false;
        """))

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    return test_engine, TestSessionLocal
