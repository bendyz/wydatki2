import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.core import asset_crypto
from app.db.session import get_db
from app.models.models import AssetAccount, AssetKeyConfig, AssetSnapshot, User
from app.schemas.assets import (
    AssetAccountCreate,
    AssetAccountResponse,
    AssetAccountUpdate,
    AssetSetupRequest,
    AssetSetupStatus,
    AssetSnapshotCreate,
    AssetSnapshotResponse,
    AssetSummaryPoint,
    AssetSummaryResponse,
    AssetVerifyRequest,
    AssetVerifyResponse,
)

router = APIRouter()


def _get_fernet(
    db: Session,
    user: User,
    password: Optional[str],
):
    if not password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wymagane hasło modułu Majątek")
    cfg = db.query(AssetKeyConfig).filter_by(user_id=user.id).first()
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Moduł Majątek nie jest skonfigurowany")
    if not asset_crypto.verify_password(password, cfg.salt, cfg.verification_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nieprawidłowe hasło modułu Majątek")
    return asset_crypto.get_fernet(password, cfg.salt)


def _decrypt_account(acc: AssetAccount, fernet) -> AssetAccountResponse:
    snapshots_dec = []
    for s in acc.snapshots:
        note = asset_crypto.decrypt(fernet, s.note_enc) if s.note_enc else None
        snapshots_dec.append(AssetSnapshotResponse(
            id=s.id,
            account_id=s.account_id,
            amount=float(asset_crypto.decrypt(fernet, s.amount_enc)),
            recorded_at=s.recorded_at,
            note=note,
        ))

    latest_amount = None
    latest_date = None
    if snapshots_dec:
        latest = max(snapshots_dec, key=lambda x: x.recorded_at)
        latest_amount = latest.amount
        latest_date = latest.recorded_at

    return AssetAccountResponse(
        id=acc.id,
        name=asset_crypto.decrypt(fernet, acc.name_enc),
        account_type=acc.account_type,
        currency=acc.currency,
        sort_order=acc.sort_order,
        latest_amount=latest_amount,
        latest_date=latest_date,
        snapshots=sorted(snapshots_dec, key=lambda x: x.recorded_at, reverse=True),
    )


# ── Setup / verify ──────────────────────────────────────────────────────────

@router.get("/setup-status", response_model=AssetSetupStatus)
def setup_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = db.query(AssetKeyConfig).filter_by(user_id=current_user.id).first()
    return AssetSetupStatus(configured=cfg is not None)


@router.post("/setup", response_model=AssetSetupStatus, status_code=status.HTTP_201_CREATED)
def setup(
    data: AssetSetupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if db.query(AssetKeyConfig).filter_by(user_id=current_user.id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Moduł Majątek jest już skonfigurowany")
    salt_hex, verification_token = asset_crypto.generate_setup(data.password)
    cfg = AssetKeyConfig(user_id=current_user.id, salt=salt_hex, verification_token=verification_token)
    db.add(cfg)
    db.commit()
    return AssetSetupStatus(configured=True)


@router.post("/verify", response_model=AssetVerifyResponse)
def verify(
    data: AssetVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = db.query(AssetKeyConfig).filter_by(user_id=current_user.id).first()
    if not cfg:
        return AssetVerifyResponse(valid=False)
    valid = asset_crypto.verify_password(data.password, cfg.salt, cfg.verification_token)
    return AssetVerifyResponse(valid=valid)


# ── Accounts ─────────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=List[AssetAccountResponse])
def list_accounts(
    x_asset_password: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fernet = _get_fernet(db, current_user, x_asset_password)
    accounts = db.query(AssetAccount).filter_by(user_id=current_user.id).order_by(AssetAccount.sort_order).all()
    return [_decrypt_account(a, fernet) for a in accounts]


@router.post("/accounts", response_model=AssetAccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    data: AssetAccountCreate,
    x_asset_password: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fernet = _get_fernet(db, current_user, x_asset_password)
    acc = AssetAccount(
        user_id=current_user.id,
        name_enc=asset_crypto.encrypt(fernet, data.name),
        account_type=data.account_type,
        currency=data.currency,
        sort_order=data.sort_order,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return _decrypt_account(acc, fernet)


@router.put("/accounts/{account_id}", response_model=AssetAccountResponse)
def update_account(
    account_id: int,
    data: AssetAccountUpdate,
    x_asset_password: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fernet = _get_fernet(db, current_user, x_asset_password)
    acc = db.query(AssetAccount).filter_by(id=account_id, user_id=current_user.id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Konto nie istnieje")
    if data.name is not None:
        acc.name_enc = asset_crypto.encrypt(fernet, data.name)
    if data.account_type is not None:
        acc.account_type = data.account_type
    if data.currency is not None:
        acc.currency = data.currency
    if data.sort_order is not None:
        acc.sort_order = data.sort_order
    db.commit()
    db.refresh(acc)
    return _decrypt_account(acc, fernet)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: int,
    x_asset_password: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fernet = _get_fernet(db, current_user, x_asset_password)  # password check
    acc = db.query(AssetAccount).filter_by(id=account_id, user_id=current_user.id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Konto nie istnieje")
    db.delete(acc)
    db.commit()


# ── Snapshots ────────────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/snapshots", response_model=AssetSnapshotResponse, status_code=status.HTTP_201_CREATED)
def add_snapshot(
    account_id: int,
    data: AssetSnapshotCreate,
    x_asset_password: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fernet = _get_fernet(db, current_user, x_asset_password)
    acc = db.query(AssetAccount).filter_by(id=account_id, user_id=current_user.id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Konto nie istnieje")
    snap = AssetSnapshot(
        account_id=account_id,
        amount_enc=asset_crypto.encrypt(fernet, str(data.amount)),
        recorded_at=data.recorded_at,
        note_enc=asset_crypto.encrypt(fernet, data.note) if data.note else None,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return AssetSnapshotResponse(
        id=snap.id,
        account_id=snap.account_id,
        amount=data.amount,
        recorded_at=snap.recorded_at,
        note=data.note,
    )


@router.delete("/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_snapshot(
    snapshot_id: int,
    x_asset_password: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fernet = _get_fernet(db, current_user, x_asset_password)  # password check
    snap = (
        db.query(AssetSnapshot)
        .join(AssetAccount)
        .filter(AssetSnapshot.id == snapshot_id, AssetAccount.user_id == current_user.id)
        .first()
    )
    if not snap:
        raise HTTPException(status_code=404, detail="Wpis nie istnieje")
    db.delete(snap)
    db.commit()


# ── Summary (chart data) ─────────────────────────────────────────────────────

@router.get("/summary", response_model=AssetSummaryResponse)
def summary(
    x_asset_password: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fernet = _get_fernet(db, current_user, x_asset_password)
    accounts = db.query(AssetAccount).filter_by(user_id=current_user.id).order_by(AssetAccount.sort_order).all()
    accounts_dec = [_decrypt_account(a, fernet) for a in accounts]

    # Collect all unique dates across all snapshots
    all_dates: set[datetime.date] = set()
    for acc in accounts_dec:
        for snap in acc.snapshots:
            all_dates.add(snap.recorded_at)

    points: list[AssetSummaryPoint] = []
    for date in sorted(all_dates):
        by_account: dict[str, float] = {}
        total = 0.0
        for acc in accounts_dec:
            # Latest snapshot up to this date
            snaps_up_to = [s for s in acc.snapshots if s.recorded_at <= date]
            if snaps_up_to:
                latest_val = max(snaps_up_to, key=lambda s: s.recorded_at).amount
                by_account[str(acc.id)] = latest_val
                total += latest_val
        points.append(AssetSummaryPoint(date=date, total=total, by_account=by_account))

    return AssetSummaryResponse(points=points, accounts=accounts_dec)
