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


# Use SSL only when connecting to Render/PostgreSQL hosted database
connect_args = {}

if "render.com" in DATABASE_URL or "onrender.com" in DATABASE_URL:
    connect_args = {"sslmode": "require"}


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,

    # Permanent production protection:
    # Checks if a database connection is alive before using it.
    # If the old connection is dead, SQLAlchemy discards it and opens a fresh one.
    pool_pre_ping=True,

    # Recycles database connections every 5 minutes.
    # This helps avoid stale SSL/PostgreSQL connections on Render.
    pool_recycle=300,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        