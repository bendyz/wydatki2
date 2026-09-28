"""Abonament ratalny po ostatniej racie (remaining_installments=0) nie może wywalać API."""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud.subscription import get_subscriptions
from app.models.models import Base, Subscription, User
from app.schemas.subscription import SubscriptionResponse


def test_exhausted_installments_serialize_and_are_not_active():
    db = sessionmaker(bind=create_engine("sqlite://"))()
    Base.metadata.create_all(db.get_bind())
    user = User(email="t@t.pl", hashed_password="x")
    db.add(user)
    db.commit()
    sub = Subscription(user_id=user.id, name="Raty", amount=10, frequency_days=30,
                       start_date=date(2026, 1, 1), next_billing_date=date(2026, 9, 1),
                       remaining_installments=0)
    db.add(sub)
    db.commit()

    SubscriptionResponse.model_validate(sub)  # przed poprawką: ValidationError gt=0
    assert get_subscriptions(db, user.id, active_only=True) == []
    assert len(get_subscriptions(db, user.id)) == 1
