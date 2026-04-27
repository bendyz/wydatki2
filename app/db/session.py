from sqlalchemy import create_engine
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
    Base.metadata.create_all(bind=engine)
