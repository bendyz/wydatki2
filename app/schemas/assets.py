import datetime
from typing import List, Optional

from pydantic import BaseModel


class AssetSetupRequest(BaseModel):
    password: str


class AssetVerifyRequest(BaseModel):
    password: str


class AssetSetupStatus(BaseModel):
    configured: bool


class AssetVerifyResponse(BaseModel):
    valid: bool


class AssetAccountCreate(BaseModel):
    name: str
    account_type: str = "other"  # cash / bank / etf / crypto / foreign / other
    currency: str = "PLN"
    sort_order: int = 0


class AssetAccountUpdate(BaseModel):
    name: Optional[str] = None
    account_type: Optional[str] = None
    currency: Optional[str] = None
    sort_order: Optional[int] = None


class AssetSnapshotCreate(BaseModel):
    amount: float
    recorded_at: datetime.date
    note: Optional[str] = None


class AssetSnapshotResponse(BaseModel):
    id: int
    account_id: int
    amount: float
    recorded_at: datetime.date
    note: Optional[str] = None

    class Config:
        from_attributes = True


class AssetAccountResponse(BaseModel):
    id: int
    name: str
    account_type: str
    currency: str
    sort_order: int
    latest_amount: Optional[float] = None
    latest_date: Optional[datetime.date] = None
    snapshots: List[AssetSnapshotResponse] = []

    class Config:
        from_attributes = True


class AssetSummaryPoint(BaseModel):
    date: datetime.date
    total: float
    by_account: dict


class AssetSummaryResponse(BaseModel):
    points: List[AssetSummaryPoint]
    accounts: List[AssetAccountResponse]
