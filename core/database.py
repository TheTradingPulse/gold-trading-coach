import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env for local dev
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Railway provides DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection(database=None):
    """Get database connection - Railway or local"""
    if DATABASE_URL:
        # Railway: use the full connection URL directly
        return psycopg2.connect(DATABASE_URL)
    else:
        # Local development
        DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = os.getenv("DB_PORT", "5432")
        DB_NAME = os.getenv("DB_NAME", "gold_trading")
        DB_USER = os.getenv("DB_USER", "postgres")
        target_db = database if database else DB_NAME
        return psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=target_db,
            user=DB_USER,
            password=DB_PASSWORD
        )


def connect():
    """Connect to PostgreSQL and return connection"""
    try:
        conn = get_connection()
        print("Connected to PostgreSQL successfully!")
        return conn
    except Exception as e:
        print(f"Connection failed: {e}")
        return None


def create_database():
    """Create the gold_trading database if it doesn't exist"""
    if DATABASE_URL:
        print("Using Railway database - skipping database creation")
        return

    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
    conn = psycopg2.connect(
        host="localhost", port="5432", database="postgres",
        user="postgres", password=DB_PASSWORD
    )
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'gold_trading'")
    exists = cursor.fetchone()
    if not exists:
        cursor.execute("CREATE DATABASE gold_trading")
        print("Database 'gold_trading' created!")
    else:
        print("Database 'gold_trading' already exists.")
    cursor.close()
    conn.close()


def create_tables():
    """Create all required tables"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gold_ohlcv (
            id SERIAL PRIMARY KEY,
            timeframe VARCHAR(10) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            open DOUBLE PRECISION,
            high DOUBLE PRECISION,
            low DOUBLE PRECISION,
            close DOUBLE PRECISION,
            volume DOUBLE PRECISION,
            UNIQUE(timeframe, timestamp)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol VARCHAR(10) DEFAULT 'GC',
            direction VARCHAR(5),
            entry DOUBLE PRECISION,
            stop DOUBLE PRECISION,
            target DOUBLE PRECISION,
            rr_ratio DOUBLE PRECISION,
            grade VARCHAR(3),
            alignment_score DOUBLE PRECISION,
            zone_type VARCHAR(10),
            outcome VARCHAR(15),
            exit_price DOUBLE PRECISION,
            pnl DOUBLE PRECISION,
            notes TEXT,
            tags TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_dna (
            id SERIAL PRIMARY KEY,
            trade_id INTEGER REFERENCES trade_journal(id),
            tag VARCHAR(50),
            UNIQUE(trade_id, tag)
        );
    """)

    conn.commit()
    print("All tables ready!")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    conn = connect()
    if conn:
        conn.close()
    create_database()
    create_tables()
    print("\nDatabase setup complete!")

# Backward compatibility
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")