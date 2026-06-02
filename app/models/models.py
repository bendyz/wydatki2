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
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class PaymentCard(Base):
    __tablename__ = "payment_cards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    last_six_digits = Column(String(6), nullable=True)
    # Warunki bezpłatnej karty w danym miesiącu
    min_transactions = Column(Integer, nullable=True)   # min N transakcji/miesiąc
    min_amount = Column(Float, nullable=True)           # min M zł/miesiąc
    rules_require_all = Column(Boolean, default=True)   # True=AND, False=OR

    user = relationship("User", back_populates="payment_cards")
    expenses = relationship("Expense", back_populates="card")

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
    payment_cards = relationship("PaymentCard", back_populates="user")
    asset_key_config = relationship("AssetKeyConfig", back_populates="user", uselist=False)
    asset_accounts = relationship("AssetAccount", back_populates="user")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "user_id", name="uq_category_name_user"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
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
    card_id = Column(Integer, ForeignKey("payment_cards.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="expenses")
    category = relationship("Category", back_populates="expenses")
    items = relationship("ExpenseItem", back_populates="expense")
    tags = relationship("Tag", secondary=expense_tags, back_populates="expenses")
    card = relationship("PaymentCard", back_populates="expenses")

    @property
    def category_name(self):
        return self.category.name if self.category else None

    @property
    def card_name(self):
        return self.card.name if self.card else None


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


class AssetKeyConfig(Base):
    __tablename__ = "asset_key_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    salt = Column(String, nullable=False)               # hex-encoded 16 random bytes
    verification_token = Column(String, nullable=False) # Fernet-encrypted known plaintext

    user = relationship("User", back_populates="asset_key_config")


class AssetAccount(Base):
    __tablename__ = "asset_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name_enc = Column(String, nullable=False)                    # encrypted
    account_type = Column(String, nullable=False, default="other")  # cash/bank/etf/crypto/foreign/other
    currency = Column(String, nullable=False, default="PLN")
    sort_order = Column(Integer, default=0)

    user = relationship("User", back_populates="asset_accounts")
    snapshots = relationship("AssetSnapshot", back_populates="account", cascade="all, delete-orphan", order_by="AssetSnapshot.recorded_at")


class AssetSnapshot(Base):
    __tablename__ = "asset_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("asset_accounts.id"), nullable=False)
    amount_enc = Column(String, nullable=False)  # encrypted float as string
    recorded_at = Column(Date, nullable=False)
    note_enc = Column(String, nullable=True)     # encrypted note, optional

    account = relationship("AssetAccount", back_populates="snapshots")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    frequency_days = Column(Integer, nullable=False)  # 30 for monthly mode (scheduling uses billing_day_of_month)
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
