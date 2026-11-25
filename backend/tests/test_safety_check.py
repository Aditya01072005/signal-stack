import os
import unittest
from unittest.mock import patch
from app.config import settings
from tests.test_db_config import get_test_db_url


class TestDatabaseSafety(unittest.TestCase):
    """Verifies that automated tests strictly refuse to run against production database."""

    def test_safety_check_fails_when_test_url_missing(self):
        """Must raise RuntimeError when TEST_DATABASE_URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as exc:
                get_test_db_url()
            self.assertIn("SAFETY CHECK FAILED: 'TEST_DATABASE_URL' is not configured", str(exc.exception))

    def test_safety_check_fails_when_pointing_to_production(self):
        """Must raise RuntimeError when TEST_DATABASE_URL matches production DATABASE_URL."""
        with patch.dict(os.environ, {"TEST_DATABASE_URL": settings.DATABASE_URL}):
            with self.assertRaises(RuntimeError) as exc:
                get_test_db_url()
            self.assertIn("points to the production database", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
