import hashlib
import unicodedata
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Category

# Neonowa paleta czytelna na ciemnym tle.
# Ta sama lista co CHART_PALETTE w static/js/app.js — zmieniaj obie naraz.
CATEGORY_PALETTE = [
    "#22d3ee",
    "#34d399",
    "#fbbf24",
    "#fb7185",
    "#a78bfa",
    "#f472b6",
    "#4ade80",
    "#60a5fa",
    "#fb923c",
    "#2dd4bf",
    "#e879f9",
    "#facc15",
]

DEFAULT_CATEGORY_ICON = "fa-tag"


def name_sort_key(name: Optional[str]) -> tuple:
    """
    Klucz sortowania alfabetycznego dla polskich nazw.

    SQLite sortuje bajtowo, więc "Łazienka" wylądowałaby za "Zwierzęta",
    a "auto" za "Zdrowie". Rozkładamy znaki na bazowe litery (NFKD zdejmuje
    ogonki i kreski), "ł" trzeba podmienić ręcznie, bo się nie rozkłada.
    """
    base = unicodedata.normalize("NFKD", name or "")
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = base.replace("ł", "l").replace("Ł", "L")
    return (base.casefold(), (name or "").casefold())

# Dobór domyślnej ikony po słowie kluczowym w nazwie kategorii.
# Kolejność ma znaczenie — pierwsze trafienie wygrywa.
ICON_KEYWORDS = [
    (("jedzen", "spożyw", "żywno", "zywno", "obiad", "restaur"), "fa-utensils"),
    (("zakup", "market", "sklep"), "fa-cart-shopping"),
    (("paliw", "benzyn", "tank"), "fa-gas-pump"),
    (("samoch", "auto", "serwis"), "fa-car"),
    (("dom", "mieszkan", "czynsz", "remont"), "fa-house"),
    (("prąd", "prad", "energi", "gaz"), "fa-bolt"),
    (("internet", "telefon", "abonament", "subskryp", "media"), "fa-wifi"),
    (("rozrywk", "kino", "film"), "fa-film"),
    (("gry", "gaming", "konsol"), "fa-gamepad"),
    (("podróż", "podroz", "wakacj", "lot"), "fa-plane"),
    (("transport", "bilet", "pkp", "komunikac"), "fa-train"),
    (("ubran", "odzież", "odziez", "buty"), "fa-shirt"),
    # "elektron" musi wyprzedzać grupę zdrowia — inaczej "leki" łapie "eLEKtronika"
    (("elektron", "sprzęt", "sprzet", "komputer"), "fa-plug"),
    (("zdrow", "lekarz", "leki", "apteka", "medyc"), "fa-heart-pulse"),
    (("sport", "siłown", "silown", "fitness"), "fa-dumbbell"),
    (("edukac", "nauk", "szkoł", "szkol", "kurs", "książk", "ksiazk"), "fa-graduation-cap"),
    (("prezent", "podarun", "święt", "swiet"), "fa-gift"),
    (("słodyc", "slodyc", "ciast", "deser"), "fa-cookie-bite"),
    (("napiw", "darowizn"), "fa-hand-holding-heart"),
    (("kredyt", "ubezpiecz", "rata", "bank"), "fa-building-columns"),
    (("zabawk",), "fa-shapes"),
    (("zwierz", "pies", "kot"), "fa-paw"),
    (("dzieck", "dzieci", "niemowl"), "fa-baby"),
    (("kaw", "cafe"), "fa-mug-hot"),
    (("alkohol", "piwo", "bar"), "fa-beer-mug-empty"),
    (("oszczędn", "oszczedn", "inwest"), "fa-piggy-bank"),
    (("higien", "kosmet", "fryzjer"), "fa-scissors"),
    (("narzędz", "narzedz", "budowl"), "fa-screwdriver-wrench"),
]


def default_icon_for(name: str) -> str:
    """Dobiera ikonę Font Awesome po słowie kluczowym w nazwie kategorii."""
    low = name.strip().lower()
    for keywords, icon in ICON_KEYWORDS:
        if any(k in low for k in keywords):
            return icon
    return DEFAULT_CATEGORY_ICON


def default_color_for(name: str) -> str:
    """
    Deterministycznie dobiera kolor z palety na podstawie nazwy kategorii.

    Dzięki temu kategoria ma stabilny kolor niezależnie od kolejności na liście
    czy liczby kategorii (wcześniej kolory na wykresie szły po indeksie tablicy).
    """
    digest = hashlib.md5(name.strip().lower().encode("utf-8")).hexdigest()
    return CATEGORY_PALETTE[int(digest, 16) % len(CATEGORY_PALETTE)]


def get_category(db: Session, category_id: int, user_id: int):
    """
    Pobiera kategorię należącą do konkretnego użytkownika.

    Args:
        db: Sesja bazy danych SQLAlchemy
        category_id: ID kategorii
        user_id: ID właściciela

    Returns:
        Obiekt Category lub None
    """
    return (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user_id)
        .first()
    )


def get_categories(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    include_global: bool = True,
) -> List[Category]:
    """
    Pobiera listę kategorii użytkownika.
    Opcjonalnie dołącza kategorie globalne (bez user_id).

    Args:
        db: Sesja bazy danych SQLAlchemy
        user_id: ID właściciela
        skip: Ilość rekordów do pominięcia (paginacja)
        limit: Maksymalna ilość rekordów
        include_global: Czy dołączyć kategorie globalne

    Returns:
        Lista obiektów Category posortowana alfabetycznie (po polsku)
    """
    query = db.query(Category).filter(
        (Category.user_id == user_id) | (Category.user_id.is_(None))
        if include_global
        else Category.user_id == user_id
    )

    # ORDER BY w SQL daje stabilną paginację; właściwe (polskie) sortowanie
    # robimy niżej w Pythonie — SQLite nie ma collacji z ogonkami.
    categories = (
        query.order_by(func.lower(Category.name)).offset(skip).limit(limit).all()
    )

    # Backfill dla kategorii sprzed migracji — dzięki temu każda kategoria ma
    # stabilny kolor i frontend nie musi mieć własnej logiki zastępczej.
    missing = [c for c in categories if not c.color or not c.icon]
    if missing:
        for c in missing:
            if not c.color:
                c.color = default_color_for(c.name)
            if not c.icon:
                c.icon = default_icon_for(c.name)
        db.commit()

    return sorted(categories, key=lambda c: name_sort_key(c.name))


def create_category(
    db: Session,
    name: str,
    user_id: int,
    color: Optional[str] = None,
    icon: Optional[str] = None,
) -> Optional[Category]:
    """
    Tworzy nową kategorię dla użytkownika.
    Brak koloru/ikony → nadawane automatycznie (kolor deterministycznie z nazwy).
    Zwraca None jeśli kategoria o tej nazwie już istnieje dla tego użytkownika.
    """
    existing = (
        db.query(Category)
        .filter(Category.name == name, Category.user_id == user_id)
        .first()
    )
    if existing:
        return None
    db_category = Category(
        name=name,
        user_id=user_id,
        color=color or default_color_for(name),
        icon=icon or default_icon_for(name),
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def update_category(
    db: Session,
    category_id: int,
    user_id: int,
    name: Optional[str] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
) -> Optional[Category]:
    """
    Aktualizuje kategorię użytkownika. Pola przekazane jako None są pomijane.

    Args:
        db: Sesja bazy danych SQLAlchemy
        category_id: ID kategorii do aktualizacji
        user_id: ID właściciela
        name: Nowa nazwa kategorii (opcjonalnie)
        color: Nowy kolor w formacie hex (opcjonalnie)
        icon: Nowa klasa ikony Font Awesome (opcjonalnie)

    Returns:
        Zaktualizowany obiekt Category lub None jeśli nie znaleziono
    """
    db_category = get_category(db, category_id=category_id, user_id=user_id)
    if not db_category:
        return None

    if name is not None:
        db_category.name = name
    if color is not None:
        db_category.color = color
    if icon is not None:
        db_category.icon = icon
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: int, user_id: int) -> bool:
    """
    Usuwa kategorię użytkownika.

    Args:
        db: Sesja bazy danych SQLAlchemy
        category_id: ID kategorii do usunięcia
        user_id: ID właściciela

    Returns:
        True jeśli usunięto, False jeśli nie znaleziono
    """
    db_category = get_category(db, category_id=category_id, user_id=user_id)
    if not db_category:
        return False

    db.delete(db_category)
    db.commit()
    return True
