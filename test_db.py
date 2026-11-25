
import os
import psycopg
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env file")

try:
    with psycopg.connect(DATABASE_URL, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()

    print("SUCCESS! Connected to Neon PostgreSQL.")
    print("Database version:", version[0])

except Exception as e:
    print("DATABASE CONNECTION FAILED")
    print("Error:", e)
