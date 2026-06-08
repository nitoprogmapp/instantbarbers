import os
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("❌ DATABASE_URL no está configurada")

# Render sometimes provides postgres:// instead of postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# Detect local database
is_local_db = (
    "localhost" in DATABASE_URL
    or "127.0.0.1" in DATABASE_URL
)

# Production PostgreSQL protection
connect_args = {}

if not is_local_db:
    connect_args = {
        "sslmode": "require",
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,

    # Checks connection before using it.
    # If the connection is dead, SQLAlchemy discards it and opens a new one.
    pool_pre_ping=True,

    # Recycles connections every 3 minutes to avoid stale PostgreSQL/SSL connections.
    pool_recycle=180,

    # Keeps pool controlled and stable for production.
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,

    # Prefer newer SQLAlchemy engine behavior.
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()