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
    Table,
)
from sqlalchemy.orm import relationship

from app.db.session import Base

# Many-to-many: expenses ↔ tags
expense_tags = Table(
    "expense_tags",
    Base.metadata,
    Column("expense_id", Integer, ForeignKey("expenses.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user = relationship("User", back_populates="tags")
    expenses = relationship("Expense", secondary=expense_tags, back_populates="tags")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    force_password_reset = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    expenses = relationship("Expense", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")
    categories = relationship("Category", back_populates="user")
    tags = relationship("Tag", back_populates="user")


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
    tags = relationship("Tag", secondary=expense_tags, back_populates="expenses")

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
    frequency_days = Column(Integer, nullable=True)  # None when billing_day_of_month is used
    billing_day_of_month = Column(Integer, nullable=True)  # 1-31; monthly mode
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # None if indefinite
    next_billing_date = Column(Date, nullable=False)
    remaining_installments = Column(Integer, nullable=True)  # None if indefinite
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    category = relationship("Category", back_populates="subscriptions")
