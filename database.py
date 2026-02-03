from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

#using temporary file-based SQLite database for persistence of render
DATABASE_URL = "sqlite:////tmp/warehouse.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
