import datetime

from app.api.v1.endpoints.assets import _build_points
from app.schemas.assets import AssetAccountResponse, AssetSnapshotResponse


def _acc(id, type, amount):
    snap = AssetSnapshotResponse(id=id, account_id=id, amount=amount, recorded_at=datetime.date(2026, 10, 1))
    return AssetAccountResponse(id=id, name="x", account_type=type, currency="PLN", sort_order=0, snapshots=[snap])


def test_loan_is_subtracted_from_net_worth():
    p = _build_points([_acc(1, "bank", 100_000), _acc(2, "loan", 40_000)])[0]
    assert p.total == 60_000 and p.debt == 40_000
    assert p.by_account["2"] == 40_000
