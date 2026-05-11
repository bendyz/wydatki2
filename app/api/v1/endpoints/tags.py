from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.crud.tag import delete_tag, get_expenses_by_tag, get_popular_tags, get_recent_tags, get_tags, get_tags_with_stats, rename_tag, set_expense_tags
from app.crud.expense import get_expense
from app.db.session import get_db
from app.models.models import User
from app.schemas.expense import ExpenseResponse
from app.schemas.tag import TagCreate, TagResponse, TagStats

router = APIRouter()


@router.get("/", response_model=List[TagResponse], summary="Lista tagów użytkownika")
def list_tags(
    recent_days: Optional[int] = Query(None),
    popular: bool = Query(False),
    limit: int = Query(10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if popular:
        return get_popular_tags(db, current_user.id, limit)
    if recent_days:
        return get_recent_tags(db, current_user.id, recent_days)
    return get_tags(db, current_user.id)


@router.get("/stats", response_model=List[TagStats], summary="Tagi ze statystykami")
def tags_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_tags_with_stats(db, current_user.id)


@router.put("/{tag_id}", response_model=TagResponse, summary="Zmień nazwę tagu")
def update_tag(
    tag_id: int,
    body: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tag = rename_tag(db, tag_id, current_user.id, body.name)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag nie istnieje")
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Usuń tag")
def remove_tag(tag_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not delete_tag(db, tag_id, current_user.id):
        raise HTTPException(status_code=404, detail="Tag nie istnieje")


@router.put("/expenses/{expense_id}", response_model=ExpenseResponse, summary="Ustaw tagi wydatku")
def update_expense_tags(
    expense_id: int,
    tag_names: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = get_expense(db, expense_id=expense_id, user_id=current_user.id)
    if not expense:
        raise HTTPException(status_code=404, detail="Wydatek nie istnieje")
    set_expense_tags(db, expense, current_user.id, tag_names)
    return expense


@router.get("/expenses", response_model=List[ExpenseResponse], summary="Wydatki z danym tagiem")
def expenses_by_tag(
    tag: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_expenses_by_tag(db, current_user.id, tag)
