from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.models import Expense, Tag


def get_tags(db: Session, user_id: int) -> List[Tag]:
    return db.query(Tag).filter(Tag.user_id == user_id).order_by(Tag.name).all()


def get_recent_tags(db: Session, user_id: int, days: int = 30) -> List[Tag]:
    cutoff = date.today() - timedelta(days=days)
    return (
        db.query(Tag)
        .join(Tag.expenses)
        .filter(Tag.user_id == user_id, Expense.date >= cutoff)
        .distinct()
        .order_by(Tag.name)
        .all()
    )


def get_popular_tags(db: Session, user_id: int, limit: int = 10, months: int = 4) -> List[Tag]:
    from sqlalchemy import func
    cutoff = date.today() - timedelta(days=months * 30)
    return (
        db.query(Tag)
        .join(Tag.expenses)
        .filter(Tag.user_id == user_id, Expense.date >= cutoff)
        .group_by(Tag.id)
        .order_by(func.count(Expense.id).desc())
        .limit(limit)
        .all()
    )


def get_or_create_tag(db: Session, user_id: int, name: str) -> Tag:
    name = name.strip().lstrip("#").lower()
    tag = db.query(Tag).filter(Tag.user_id == user_id, Tag.name == name).first()
    if not tag:
        tag = Tag(name=name, user_id=user_id)
        db.add(tag)
        db.commit()
        db.refresh(tag)
    return tag


def set_expense_tags(db: Session, expense: Expense, user_id: int, tag_names: List[str]):
    tags = [get_or_create_tag(db, user_id, n) for n in tag_names if n.strip()]
    expense.tags = tags
    db.commit()
    db.refresh(expense)


def delete_tag(db: Session, tag_id: int, user_id: int) -> bool:
    tag = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == user_id).first()
    if not tag:
        return False
    db.delete(tag)
    db.commit()
    return True


def get_tags_with_stats(db: Session, user_id: int) -> list:
    from sqlalchemy import func
    rows = (
        db.query(
            Tag,
            func.count(Expense.id).label("expense_count"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .outerjoin(Tag.expenses)
        .filter(Tag.user_id == user_id)
        .group_by(Tag.id)
        .order_by(Tag.name)
        .all()
    )
    return [
        {"id": tag.id, "name": tag.name, "expense_count": cnt, "total_amount": float(total)}
        for tag, cnt, total in rows
    ]


def rename_tag(db: Session, tag_id: int, user_id: int, new_name: str) -> Optional[Tag]:
    tag = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == user_id).first()
    if not tag:
        return None
    tag.name = new_name.strip().lstrip("#").lower()
    db.commit()
    db.refresh(tag)
    return tag


def get_expenses_by_tag(db: Session, user_id: int, tag_name: str):
    name = tag_name.strip().lstrip("#").lower()
    return (
        db.query(Expense)
        .join(Expense.tags)
        .filter(Tag.user_id == user_id, Tag.name == name, Expense.user_id == user_id)
        .order_by(Expense.date.desc())
        .all()
    )
