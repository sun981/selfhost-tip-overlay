"""
Omise adapter — reconciliation list (list_recent) against Omise's real list shape.

Omise list endpoints (https://docs.omise.co/api-pagination) are OFFSET-based:
  request:  from / to (ISO 8601 UTC), offset, limit (max 100), order
  response: {"object": "list", "data": [...], "offset", "limit", "total", "from", "to", ...}
There is no `has_more` / `pagination` key and no `starting_after` cursor (those are Stripe).

The fake server below slices a charge list by `offset`/`limit` exactly like Omise does, so
the test fails if the adapter stops after one page or sends Stripe-style params.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from core.payment.omise import OmiseAdapter

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _charge(i: int, status: str = "successful") -> dict:
    return {
        "object": "charge",
        "id": f"chrg_test_{i:04d}",
        "amount": 2000 + i,
        "currency": "thb",
        "status": status,
        "paid": status == "successful",
        "paid_at": "2026-10-30T01:00:00Z" if status == "successful" else None,
        "metadata": {"supporter_name": f"fan{i}", "message": "hi"},
        "source": {"object": "source", "type": "promptpay"},
    }


def _install_fake_omise(monkeypatch, charges: list[dict]) -> list[dict]:
    """Patch httpx.Client in the adapter with an offset-paginating fake. Returns call log."""
    calls: list[dict] = []

    class FakeResp:
        def __init__(self, body: dict) -> None:
            self._body = body
            self.status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return self._body

    class FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, path, params=None):
            params = dict(params or {})
            calls.append(params)
            offset = int(params.get("offset", 0))
            limit = min(int(params.get("limit", 20)), 100)
            return FakeResp({
                "object": "list",
                "data": charges[offset:offset + limit],
                "limit": limit,
                "offset": offset,
                "total": len(charges),
                "order": params.get("order", "chronological"),
                "location": "/charges",
                "from": params.get("from", "1970-01-01T00:00:00Z"),
                "to": "2026-10-30T02:00:00Z",
            })

    monkeypatch.setattr("core.payment.omise.httpx.Client", FakeClient)
    return calls


def _adapter() -> OmiseAdapter:
    from tests.conftest import TEST_SECRET_B64
    return OmiseAdapter(secret_key="skey_test_fixture", webhook_secret_b64=TEST_SECRET_B64)


def test_list_recent_reads_every_page(monkeypatch):
    """More than one page (limit 100) → every charge is returned, not just the oldest 100."""
    charges = [_charge(i) for i in range(230)]
    calls = _install_fake_omise(monkeypatch, charges)

    rows = _adapter().list_recent(datetime(2026, 10, 29, 1, 0, tzinfo=timezone.utc))

    assert [r.charge_id for r in rows] == [c["id"] for c in charges]
    assert [c["offset"] for c in calls] == [0, 100, 200]
    assert all("starting_after" not in c for c in calls), "Omise has no cursor param"


def test_list_recent_sends_iso8601_from(monkeypatch):
    """`from` must be ISO 8601 UTC (Omise docs), not a unix integer."""
    calls = _install_fake_omise(monkeypatch, [_charge(1)])

    _adapter().list_recent(datetime(2026, 10, 29, 8, 30, 15, tzinfo=timezone.utc))

    assert calls[0]["from"] == "2026-10-29T08:30:15Z"
    assert ISO_UTC.match(calls[0]["from"])


def test_list_recent_converts_non_utc_since(monkeypatch):
    """A timezone-aware `since` in another zone is converted to UTC before sending."""
    from datetime import timedelta
    calls = _install_fake_omise(monkeypatch, [])

    bangkok = timezone(timedelta(hours=7))
    _adapter().list_recent(datetime(2026, 10, 29, 15, 30, 15, tzinfo=bangkok))

    assert calls[0]["from"] == "2026-10-29T08:30:15Z"


def test_list_recent_returns_only_successful(monkeypatch):
    """The list includes pending/failed/expired charges — only successful ones come back."""
    charges = [
        _charge(1, "successful"),
        _charge(2, "pending"),
        _charge(3, "failed"),
        _charge(4, "expired"),
        _charge(5, "successful"),
    ]
    _install_fake_omise(monkeypatch, charges)

    rows = _adapter().list_recent(datetime(2026, 10, 29, tzinfo=timezone.utc))

    assert [r.charge_id for r in rows] == ["chrg_test_0001", "chrg_test_0005"]
    assert rows[0].paid_at == datetime(2026, 10, 30, 1, 0, tzinfo=timezone.utc)
    assert rows[0].metadata["supporter_name"] == "fan1"


def test_list_recent_empty_list_single_call(monkeypatch):
    calls = _install_fake_omise(monkeypatch, [])

    assert _adapter().list_recent(datetime(2026, 10, 29, tzinfo=timezone.utc)) == []
    assert len(calls) == 1
