from datetime import datetime

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
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    )  # Null for global categories

    # Relationships
    user = relationship("User", back_populates="categories")
    expenses = relationship("Expense", back_populates="category")
    subscriptions = relationship("Subscription", back_populates="category")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    metadata_ai = Column(String, nullable=True)  # JSON string for AI analysis results

    # Relationships
    user = relationship("User", back_populates="expenses")
    category = relationship("Category", back_populates="expenses")
    items = relationship("ExpenseItem", back_populates="expense")


class ExpenseItem(Base):
    __tablename__ = "expense_items"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Float, default=1.0)

    # Relationships
    expense = relationship("Expense", back_populates="items")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    frequency_days = Column(Integer, nullable=False)  # e.g., 30 for monthly
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # None if indefinite
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    category = relationship("Category", back_populates="subscriptions")
