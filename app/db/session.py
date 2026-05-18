from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Bazowa klasa dla wszystkich modeli SQLAlchemy 2.0"""

    pass


# Silnik połączenia z bazą SQLite
engine = create_engine(
    settings.database.url,
    connect_args={
        "check_same_thread": False
    },  # Niezbędne dla SQLite w środowisku wielowątkowym (FastAPI)
)

# Klasa fabrykująca sesje dla każdego zapytania
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency (zależność) do użycia w endpointach FastAPI.
    Tworzy sesję bazy danych dla każdego zapytania i zamyka ją po zakończeniu.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Inicjalizuje bazę danych – tworzy wszystkie tabele na podstawie modeli.
    Wywoływane przy starcie aplikacji.
    """
    Base.metadata.create_all(bind=engine)  # tworzy nowe tabele (tags, expense_tags)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0 NOT NULL"))
            conn.commit()
        except Exception:
            pass  # kolumna już istnieje
        # Upewnij się, że user id=1 jest adminem (dla istniejących baz)
        conn.execute(text("UPDATE users SET is_admin = 1 WHERE id = 1 AND is_admin = 0"))
        conn.commit()
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN force_password_reset BOOLEAN DEFAULT 0 NOT NULL"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN billing_day_of_month INTEGER"))
            conn.commit()
        except Exception:
            pass
        # Migrate categories: UNIQUE(name) → UNIQUE(name, user_id)
        row = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='categories'"
        )).fetchone()
        if row and "name, user_id" not in row[0]:
            conn.execute(text("PRAGMA foreign_keys=off"))
            conn.execute(text("""
                CREATE TABLE categories_new (
                    id INTEGER NOT NULL,
                    name VARCHAR NOT NULL,
                    user_id INTEGER,
                    PRIMARY KEY (id),
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    UNIQUE (name, user_id)
                )
            """))
            conn.execute(text("INSERT INTO categories_new SELECT id, name, user_id FROM categories"))
            conn.execute(text("DROP TABLE categories"))
            conn.execute(text("ALTER TABLE categories_new RENAME TO categories"))
            conn.execute(text("PRAGMA foreign_keys=on"))
            conn.commit()
