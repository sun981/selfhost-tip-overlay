"""
process_tip pipeline — Safe Edge (ARCHITECTURE §12.2, D11).

This is the single seam between "verified successful charge" and "push to overlay".
Stages run in order; any failure → fallback in webhook handler (P0#3).

PoC has 1 real stage + seam for future:
  1. amount_tiers  — hide message if below tier minimum (config-driven)
  2. word_filter   — mask banned words (config-driven)

Adding a stage: append to _STAGES. Each stage: (TipEvent) -> TipEvent | DROP | HOLD
"""
from __future__ import annotations

from contracts.events import TipEvent, StageResult
from app.stages import amount_tiers, word_filter

_STAGES = [
    amount_tiers.process,
    word_filter.process,
]


def process_tip(event: TipEvent) -> StageResult:
    """
    Run all stages in order. Returns processed event, DROP, or HOLD.
    Caller (webhook handler) wraps this in try/except + timeout.
    If any stage crashes → caller catches exception → fallback base event.
    """
    result: StageResult = event

    for stage in _STAGES:
        if isinstance(result, str):  # DROP or HOLD — stop pipeline
            return result
        result = stage(result)

    return result
