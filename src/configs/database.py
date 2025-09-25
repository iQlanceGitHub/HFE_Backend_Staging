# from sqlalchemy import create_engine
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from src.configs.config import EnvVar

SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{os.environ.get(EnvVar.DbUser.value)}:"
    f"{os.environ.get(EnvVar.DbPassword.value)}@"
    f"{os.environ.get(EnvVar.DbHost.value)}:"
    f"{os.environ.get(EnvVar.DbPort.value)}/"
    f"{os.environ.get(EnvVar.DbName.value)}"
)


engine = create_engine(SQLALCHEMY_DATABASE_URL,pool_size=50,pool_timeout=10,max_overflow=100)


# engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={
#                        "check_same_thread": False})

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
