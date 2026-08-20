import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_PASSWORD = os.getenv("DB_PASSWORD")

def connect():
    """Connect to PostgreSQL and return connection"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="postgres",
            user="postgres",
            password=DB_PASSWORD
        )
        print("Connected to PostgreSQL successfully!")
        return conn
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

def create_database():
    """Create the gold_trading database if it doesn't exist"""
    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        database="postgres",
        user="postgres",
        password=DB_PASSWORD
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
    """Create the OHLCV table in gold_trading database"""
    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        database="gold_trading",
        user="postgres",
        password=DB_PASSWORD
    )
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
    
    conn.commit()
    print("Table 'gold_ohlcv' ready!")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    conn = connect()
    if conn:
        conn.close()
    
    create_database()
    create_tables()
    
    print("\nDatabase setup complete!")