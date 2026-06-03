"""
Stable contracts between Secure Core and Safe Edge.
ARCHITECTURE §12.2 — TipEvent, OverlayEvent, stage protocol.

WARNING: Changing field names here breaks core ↔ app. Ask before editing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal

# ── Canonical event flowing from verified charge → process_tip → overlay ──

@dataclass
class TipEvent:
    charge_id: str
    amount: int                 # satang (1 THB = 100 satang)
    currency: str               # always "thb"
    supporter_name: str
    message: str
    paid_at: datetime
    source_type: str            # "promptpay"

    # Seam fields — unused in PoC, stable for future stages
    tts_audio_url: str | None = field(default=None)
    flagged: bool = field(default=False)


@dataclass
class OverlayEvent:
    charge_id: str
    amount: int                 # satang — divide by 100 at render
    supporter_name: str
    message: str                # may be empty if amount-tier hides it
    event_seq: int

    # Seam fields — unused in PoC
    tts_audio_url: str | None = field(default=None)


# ── Stage protocol ──

StageResult = TipEvent | Literal["DROP"] | Literal["HOLD"]
StageCallable = Callable[[TipEvent], StageResult]
