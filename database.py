"""
СУЖЦД — настройка базы данных SQLite + SQLAlchemy
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base

DATABASE_URL = "sqlite:///./sujzd.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)
    # Миграция: добавить новые колонки если не существуют (SQLite не поддерживает IF NOT EXISTS через ORM)
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE notifications ADD COLUMN norm_ref VARCHAR(128) DEFAULT ''",
            "ALTER TABLE notifications ADD COLUMN source_field VARCHAR(64) DEFAULT ''",
            "ALTER TABLE notifications ADD COLUMN target_doc_id VARCHAR(32)",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # колонка уже существует


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
