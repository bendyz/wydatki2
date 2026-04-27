from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.models import Expense, ExpenseItem


def get_expense(db: Session, expense_id: int, user_id: int) -> Optional[Expense]:
    """
    Pobiera pojedynczy wydatek należący do użytkownika.

    Args:
        db: Sesja bazy danych SQLAlchemy
        expense_id: ID wydatku
        user_id: ID właściciela

    Returns:
        Obiekt Expense lub None
    """
    return (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == user_id)
        .first()
    )


def get_expenses(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    item_category_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Expense]:
    """
    Pobiera listę wydatków użytkownika z opcjonalnym filtrowaniem.

    Args:
        db: Sesja bazy danych SQLAlchemy
        user_id: ID właściciela
        skip: Ilość rekordów do pominięcia (paginacja)
        limit: Maksymalna ilość rekordów
        category_id: Opcjonalne filtrowanie po kategorii ogólnej wydatku
        item_category_id: Opcjonalne filtrowanie po kategorii pozycji (item)
        start_date: Opcjonalne filtrowanie od daty (YYYY-MM-DD)
        end_date: Opcjonalne filtrowanie do daty (YYYY-MM-DD)

    Returns:
        Lista obiektów Expense posortowana malejąco po dacie
    """
    query = db.query(Expense).filter(Expense.user_id == user_id)

    if category_id is not None:
        query = query.filter(Expense.category_id == category_id)
    if item_category_id is not None:
        query = (
            query.join(ExpenseItem)
            .filter(ExpenseItem.category_id == item_category_id)
            .distinct()
        )
    if start_date is not None:
        query = query.filter(Expense.date >= start_date)
    if end_date is not None:
        query = query.filter(Expense.date <= end_date)

    return query.order_by(Expense.date.desc()).offset(skip).limit(limit).all()


def create_expense(
    db: Session,
    user_id: int,
    amount: float,
    description: Optional[str],
    expense_date: date,
    category_id: Optional[int],
    items: List[dict],
    metadata_ai: Optional[str] = None,
    receipt_image_path: Optional[str] = None,
) -> Expense:
    """
    Tworzy nowy wydatek wraz z pozycjami (items).

    Args:
        db: Sesja bazy danych SQLAlchemy
        user_id: ID właściciela
        amount: Całkowita kwota wydatku
        description: Opis / nazwa sklepu
        expense_date: Data wydatku
        category_id: ID kategorii ogólnej dla całego wydatku (opcjonalne)
        items: Lista słowników z pozycjami, np. [{"name": "Chleb", "price": 5.50, "quantity": 2, "category_id": 1}]
        metadata_ai: Surowe dane z analizy AI (opcjonalne)
        receipt_image_path: Ścieżka do zdjęcia paragonu (opcjonalne)

    Returns:
        Utworzony obiekt Expense z załadowanymi pozycjami
    """
    db_expense = Expense(
        user_id=user_id,
        amount=amount,
        description=description,
        date=expense_date,
        category_id=category_id,
        metadata_ai=metadata_ai,
        receipt_image_path=receipt_image_path,
    )
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)

    # Dodaj pozycje wydatku
    for item_data in items:
        db_item = ExpenseItem(
            expense_id=db_expense.id,
            name=item_data["name"],
            price=item_data["price"],
            quantity=item_data.get("quantity", 1.0),
            category_id=item_data.get("category_id"),
        )
        db.add(db_item)

    db.commit()
    db.refresh(db_expense)
    return db_expense


def update_expense(
    db: Session,
    expense_id: int,
    user_id: int,
    amount: Optional[float] = None,
    description: Optional[str] = None,
    expense_date: Optional[date] = None,
    category_id: Optional[int] = None,
    items: Optional[List[dict]] = None,
    receipt_image_path: Optional[str] = None,
) -> Optional[Expense]:
    """
    Aktualizuje wydatek użytkownika.
    Jeśli przekazano nowe pozycje (items), stare zostaną usunięte i zastąpione nowymi.

    Args:
        db: Sesja bazy danych SQLAlchemy
        expense_id: ID wydatku do aktualizacji
        user_id: ID właściciela
        amount: Nowa kwota
        description: Nowy opis
        expense_date: Nowa data
        category_id: Nowa kategoria ogólna
        items: Nowa lista pozycji (opcjonalna)
        receipt_image_path: Nowa ścieżka do zdjęcia paragonu (opcjonalna)

    Returns:
        Zaktualizowany obiekt Expense lub None jeśli nie znaleziono
    """
    db_expense = get_expense(db, expense_id=expense_id, user_id=user_id)
    if not db_expense:
        return None

    if amount is not None:
        db_expense.amount = amount
    if description is not None:
        db_expense.description = description
    if expense_date is not None:
        db_expense.date = expense_date
    if category_id is not None:
        db_expense.category_id = category_id
    if receipt_image_path is not None:
        db_expense.receipt_image_path = receipt_image_path

    # Jeśli przekazano nowe pozycje, usuń stare i dodaj nowe
    if items is not None:
        db.query(ExpenseItem).filter(ExpenseItem.expense_id == expense_id).delete()

        for item_data in items:
            db_item = ExpenseItem(
                expense_id=expense_id,
                name=item_data["name"],
                price=item_data["price"],
                quantity=item_data.get("quantity", 1.0),
                category_id=item_data.get("category_id"),
            )
            db.add(db_item)

    db.commit()
    db.refresh(db_expense)
    return db_expense


def delete_expense(db: Session, expense_id: int, user_id: int) -> bool:
    """
    Usuwa wydatek użytkownika wraz ze wszystkimi jego pozycjami.

    Args:
        db: Sesja bazy danych SQLAlchemy
        expense_id: ID wydatku do usunięcia
        user_id: ID właściciela

    Returns:
        True jeśli usunięto, False jeśli nie znaleziono
    """
    db_expense = get_expense(db, expense_id=expense_id, user_id=user_id)
    if not db_expense:
        return False

    # Usuń powiązane pozycje explicite (na wypadek braku cascade w modelu)
    db.query(ExpenseItem).filter(ExpenseItem.expense_id == expense_id).delete()

    db.delete(db_expense)
    db.commit()
    return True
