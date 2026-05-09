import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    expenses = relationship("Expense", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")
    categories = relationship("Category", back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # Nullable for global/system categories

    # Relationships
    user = relationship("User", back_populates="categories")
    expenses = relationship("Expense", back_populates="category")
    subscriptions = relationship("Subscription", back_populates="category")
    items = relationship("ExpenseItem", back_populates="category")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    # Field to store metadata from AI (e.g., shop name)
    metadata_ai = Column(String, nullable=True)
    # Path to the processed receipt image on filesystem
    receipt_image_path = Column(String, nullable=True)

    # Relationships
    user = relationship("User", back_populates="expenses")
    category = relationship("Category", back_populates="expenses")
    items = relationship("ExpenseItem", back_populates="expense")

    @property
    def category_name(self):
        return self.category.name if self.category else None


class ExpenseItem(Base):
    __tablename__ = "expense_items"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Float, default=1.0)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Relationships
    expense = relationship("Expense", back_populates="items")
    category = relationship("Category", back_populates="items")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    frequency_days = Column(Integer, nullable=False)  # e.g., 30 for monthly
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # None if indefinite
    next_billing_date = Column(Date, nullable=False)
    remaining_installments = Column(Integer, nullable=True)  # None if indefinite
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    category = relationship("Category", back_populates="subscriptions")
