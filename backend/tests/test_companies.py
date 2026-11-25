import concurrent.futures
import unittest
import uuid
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.api.v1.companies import get_company, list_companies, register_company, update_company
from app.models.company import Company
from app.schemas.company import (
    CompanyCreate,
    CompanyUpdate,
    normalize_website_url,
)
from tests.test_db_config import create_test_engine_and_session


class TestCompanyAPI(unittest.TestCase):
    """Isolated test suite for Company Setup, URL Canonicalization, and Duplicate Protection."""

    @classmethod
    def setUpClass(cls):
        """Initializes the isolated PostgreSQL test database schema."""
        cls.test_engine, cls.TestSession = create_test_engine_and_session()

    def setUp(self):
        self.db = self.TestSession()
        self.created_ids = []

    def tearDown(self):
        """Cleans up any created test records in the isolated database."""
        if self.created_ids:
            self.db.execute(delete(Company).where(Company.id.in_(self.created_ids)))
            self.db.commit()
        self.db.close()

    def test_url_canonicalization_all_cases(self):
        """
        Verifies all 7 required canonicalization edge cases:
        1. https://example.com
        2. https://example.com/
        3. https://example.com?ref=home
        4. https://example.com#section
        5. https://example.com/About
        6. https://example.com/about
        7. https://example.com:8080/About
        """
        # Case 1 & 2: Root URL and trailing-slash variation normalize identically
        self.assertEqual(normalize_website_url("https://example.com"), "https://example.com")
        self.assertEqual(normalize_website_url("https://example.com/"), "https://example.com")
        self.assertEqual(normalize_website_url("HTTPS://EXAMPLE.COM/"), "https://example.com")

        # Case 3: Query without slash after hostname preserves query case
        self.assertEqual(normalize_website_url("https://example.com?ref=home"), "https://example.com?ref=home")
        self.assertEqual(normalize_website_url("https://example.com/?ref=home"), "https://example.com?ref=home")
        self.assertEqual(normalize_website_url("HTTPS://EXAMPLE.COM?REF=HOME"), "https://example.com?REF=HOME")

        # Case 4: Fragment without slash after hostname preserves fragment case
        self.assertEqual(normalize_website_url("https://example.com#section"), "https://example.com#section")
        self.assertEqual(normalize_website_url("https://example.com/#section"), "https://example.com#section")
        self.assertEqual(normalize_website_url("HTTPS://EXAMPLE.COM#SECTION"), "https://example.com#SECTION")

        # Case 5 & 6: Distinct path casing preserved
        self.assertEqual(normalize_website_url("https://example.com/About"), "https://example.com/About")
        self.assertEqual(normalize_website_url("https://example.com/About/"), "https://example.com/About")
        self.assertEqual(normalize_website_url("https://example.com/about"), "https://example.com/about")
        self.assertNotEqual(normalize_website_url("https://example.com/About"), normalize_website_url("https://example.com/about"))

        # Case 7: Port + path case preserved
        self.assertEqual(normalize_website_url("https://example.com:8080/About"), "https://example.com:8080/About")
        self.assertEqual(normalize_website_url("HTTPS://EXAMPLE.COM:8080/About/"), "https://example.com:8080/About")

    def test_scheme_and_hostname_case_variations_are_duplicates(self):
        """Scheme and hostname case variations trigger HTTP 409 duplicate conflict."""
        uid = uuid.uuid4().hex[:8]
        website_original = f"https://dup-host-{uid}.org:8080/About"
        website_upper_host = f"HTTPS://DUP-HOST-{uid.upper()}.ORG:8080/About"

        c1 = register_company(CompanyCreate(name=f"Entity {uid}", website_url=website_original), db=self.db)
        self.created_ids.append(c1.id)

        # Uppercase scheme/host variation
        with self.assertRaises(HTTPException) as exc:
            register_company(CompanyCreate(name="Duplicate Host Attempt", website_url=website_upper_host), db=self.db)
        self.assertEqual(exc.exception.status_code, 409)

    def test_trailing_slash_variations_are_duplicates(self):
        """Trailing-slash variations on root and subpaths trigger HTTP 409 duplicate conflict."""
        uid = uuid.uuid4().hex[:8]
        root_no_slash = f"https://dup-root-{uid}.org"
        root_with_slash = f"https://dup-root-{uid}.org/"

        c1 = register_company(CompanyCreate(name=f"Root {uid}", website_url=root_no_slash), db=self.db)
        self.created_ids.append(c1.id)

        # Root with trailing slash
        with self.assertRaises(HTTPException) as exc:
            register_company(CompanyCreate(name="Duplicate Root Attempt", website_url=root_with_slash), db=self.db)
        self.assertEqual(exc.exception.status_code, 409)

        # Path with trailing slash
        path_no_slash = f"https://dup-path-{uid}.org/Team"
        path_with_slash = f"https://dup-path-{uid}.org/Team/"

        c2 = register_company(CompanyCreate(name=f"Path {uid}", website_url=path_no_slash), db=self.db)
        self.created_ids.append(c2.id)

        with self.assertRaises(HTTPException) as exc2:
            register_company(CompanyCreate(name="Duplicate Path Attempt", website_url=path_with_slash), db=self.db)
        self.assertEqual(exc2.exception.status_code, 409)

    def test_query_without_slash_variations_are_duplicates(self):
        """Query variations with and without slash after host are treated consistently as duplicates."""
        uid = uuid.uuid4().hex[:8]
        url_without_slash = f"https://query-{uid}.org?ref=home"
        url_with_slash = f"https://query-{uid}.org/?ref=home"

        c1 = register_company(CompanyCreate(name=f"Query {uid}", website_url=url_without_slash), db=self.db)
        self.created_ids.append(c1.id)

        with self.assertRaises(HTTPException) as exc:
            register_company(CompanyCreate(name="Duplicate Query Attempt", website_url=url_with_slash), db=self.db)
        self.assertEqual(exc.exception.status_code, 409)

    def test_distinct_path_casing_allowed(self):
        """/About and /about are treated as distinct paths and both register successfully."""
        uid = uuid.uuid4().hex[:8]
        url_upper = f"https://distinct-{uid}.org/About"
        url_lower = f"https://distinct-{uid}.org/about"

        c1 = register_company(CompanyCreate(name=f"Entity Upper {uid}", website_url=url_upper), db=self.db)
        self.created_ids.append(c1.id)
        self.assertEqual(c1.website_url, url_upper)

        c2 = register_company(CompanyCreate(name=f"Entity Lower {uid}", website_url=url_lower), db=self.db)
        self.created_ids.append(c2.id)
        self.assertEqual(c2.website_url, url_lower)
        self.assertNotEqual(c1.id, c2.id)

    def test_soft_deleted_company_url_can_be_registered_again(self):
        """A soft-deleted company's URL can be registered again (WHERE is_deleted = false)."""
        uid = uuid.uuid4().hex[:8]
        website = f"https://reuse-{uid}.org/Page"

        c1 = register_company(CompanyCreate(name=f"Original {uid}", website_url=website), db=self.db)
        self.created_ids.append(c1.id)

        # Soft delete
        c1_record = self.db.get(Company, c1.id)
        c1_record.is_deleted = True
        self.db.commit()

        # Re-register
        c2 = register_company(CompanyCreate(name=f"Re-registered {uid}", website_url=website), db=self.db)
        self.created_ids.append(c2.id)
        self.assertIsNotNone(c2.id)
        self.assertFalse(c2.is_deleted)

    def test_concurrent_duplicate_registrations(self):
        """
        Simulates two threads attempting to register the exact same website URL concurrently.
        Exactly one succeeds (201) and the other returns HTTP 409.
        """
        uid = uuid.uuid4().hex[:8]
        website = f"https://race-{uid}.org/Home"

        results = []

        def register_worker(name_suffix: str):
            worker_db = self.TestSession()
            try:
                payload = CompanyCreate(name=f"Worker {name_suffix}", website_url=website)
                res = register_company(payload, db=worker_db)
                return ("success", res.id)
            except HTTPException as e:
                return ("error", e.status_code)
            finally:
                worker_db.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(register_worker, "A")
            f2 = executor.submit(register_worker, "B")
            results.append(f1.result())
            results.append(f2.result())

        statuses = [r[0] for r in results]
        self.assertIn("success", statuses)
        self.assertIn("error", statuses)

        for status, val in results:
            if status == "success":
                self.created_ids.append(val)
            elif status == "error":
                self.assertEqual(val, 409)

    def test_database_level_canonical_index_enforcement(self):
        """
        Tests direct SQL insertion bypassing API logic to verify the PostgreSQL index
        enforces canonical uniqueness directly in the database engine.
        """
        uid = uuid.uuid4().hex[:8]
        website_canonical = f"https://direct-{uid}.org/About"
        website_raw_variant = f"HTTPS://DIRECT-{uid.upper()}.ORG/About"

        # Direct insert 1
        c1 = Company(name="Direct 1", website_url=website_canonical, is_deleted=False)
        self.db.add(c1)
        self.db.commit()
        self.created_ids.append(c1.id)

        # Direct insert 2 with uppercase scheme/host -> Expect IntegrityError from DB index
        c2 = Company(name="Direct 2 Variant", website_url=website_raw_variant, is_deleted=False)
        self.db.add(c2)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

        # Direct insert 3 with lowercase /about -> Must SUCCEED as distinct path
        c3 = Company(name="Direct 3 Distinct", website_url=f"https://direct-{uid}.org/about", is_deleted=False)
        self.db.add(c3)
        self.db.commit()
        self.created_ids.append(c3.id)

        # Direct insert 4 with trailing slash variant -> Expect IntegrityError from DB index
        c4 = Company(name="Direct 4 Slash Variant", website_url=f"https://direct-{uid}.org/About/", is_deleted=False)
        self.db.add(c4)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
