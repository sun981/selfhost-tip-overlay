"""
Startup self-test — Secure Core.
WARNING: security-critical. Human review required before editing. See core/AGENTS.md.

Runs before the server accepts any requests.
If any assertion fails → sys.exit (fail-closed, ARCHITECTURE §13.2).

NOTE on test vectors: No official Omise published test vector exists (confirmed via
docs fetch). The vectors here are self-consistency checks — they prove verify_webhook
is internally consistent (build-wrong-but-consistently would still pass). Real
ground-truth validation requires testing against an actual Omise test-mode webhook
per SPEC §11. Label: "self-consistency, not ground-truth".
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys
import time


def run() -> None:
    """Run all startup self-tests. sys.exit on any failure."""
    failures: list[str] = []

    # Fire bad-signature / replay / missing-header vectors against the SELECTED gateway
    # adapter (ARCHITECTURE §9.5 — prove the active verify_webhook rejects forgery).
    gateway = os.environ.get("PAYMENT_GATEWAY", "omise").strip().lower()
    if gateway == "stripe":
        _test_stripe_bad_sig(failures)
        _test_stripe_replay(failures)
        _test_stripe_missing_headers(failures)
    else:
        _test_sig_verify_bad_sig(failures)
        _test_sig_verify_replay(failures)
        _test_sig_verify_missing_headers(failures)

    _test_cors_not_wildcard(failures)
    _test_debug_off(failures)

    if failures:
        print("\n[STARTUP SELF-TEST FAILED]", flush=True)
        for f in failures:
            print(f"  FAIL: {f}", flush=True)
        print("Fix the issues above before running in production.\n", flush=True)
        sys.exit(1)

    print("[Startup self-test] OK", flush=True)


def _make_valid_sig(secret_b64: str, ts_str: str, raw_body: bytes) -> str:
    key = base64.b64decode(secret_b64, validate=True)
    signed = ts_str.encode() + b"." + raw_body
    return hmac.new(key, signed, hashlib.sha256).hexdigest()


def _test_sig_verify_bad_sig(failures: list[str]) -> None:
    """Bad signature must raise SignatureError (self-consistency check)."""
    from core.payment.omise import OmiseAdapter, SignatureError

    secret_b64 = base64.b64encode(b"test-secret-key-32-bytes-padding").decode()
    adapter = OmiseAdapter(secret_key="skey_test_dummy", webhook_secret_b64=secret_b64)

    ts_str = str(int(time.time()))
    raw_body = b'{"key":"charge.complete","data":{"object":"charge","id":"chrg_test"}}'
    bad_sig = "0" * 64

    headers = {
        "omise-signature-timestamp": ts_str,
        "omise-signature": bad_sig,
    }

    try:
        adapter.verify_webhook(raw_body, headers)
        failures.append("Bad signature should have raised SignatureError but did not")
    except SignatureError:
        pass  # Expected
    except Exception as e:
        failures.append(f"Bad signature raised wrong exception type: {type(e).__name__}: {e}")


def _test_sig_verify_replay(failures: list[str]) -> None:
    """Timestamp outside ±5min must raise ReplayError (self-consistency check)."""
    from core.payment.omise import OmiseAdapter, ReplayError, SignatureError

    secret_b64 = base64.b64encode(b"test-secret-key-32-bytes-padding").decode()
    adapter = OmiseAdapter(secret_key="skey_test_dummy", webhook_secret_b64=secret_b64)

    old_ts_str = str(int(time.time()) - 400)  # 400s ago — outside 300s window
    raw_body = b'{"key":"charge.complete","data":{}}'
    good_sig = _make_valid_sig(secret_b64, old_ts_str, raw_body)

    headers = {
        "omise-signature-timestamp": old_ts_str,
        "omise-signature": good_sig,
    }

    try:
        adapter.verify_webhook(raw_body, headers)
        failures.append("Old timestamp should have raised ReplayError but did not")
    except ReplayError:
        pass  # Expected
    except SignatureError:
        failures.append("Old timestamp raised SignatureError instead of ReplayError")
    except Exception as e:
        failures.append(f"Old timestamp raised wrong exception: {type(e).__name__}: {e}")


def _test_sig_verify_missing_headers(failures: list[str]) -> None:
    """Missing headers must raise SignatureError (not crash to 500)."""
    from core.payment.omise import OmiseAdapter, SignatureError

    secret_b64 = base64.b64encode(b"test-secret-key-32-bytes-padding").decode()
    adapter = OmiseAdapter(secret_key="skey_test_dummy", webhook_secret_b64=secret_b64)

    raw_body = b'{"key":"charge.complete"}'

    try:
        adapter.verify_webhook(raw_body, {})  # empty headers
        failures.append("Missing headers should have raised SignatureError but did not")
    except SignatureError:
        pass  # Expected
    except Exception as e:
        failures.append(f"Missing headers raised wrong exception: {type(e).__name__}: {e}")


def _stripe_sign(secret: str, ts: str, raw_body: bytes) -> str:
    signed = ts.encode() + b"." + raw_body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def _test_stripe_bad_sig(failures: list[str]) -> None:
    """Bad Stripe signature must raise SignatureError (self-consistency check)."""
    from core.payment.base import SignatureError
    from core.payment.stripe import StripeAdapter

    adapter = StripeAdapter(secret_key="sk_test_dummy", webhook_secret="whsec_dummy")
    ts = str(int(time.time()))
    raw_body = b'{"type":"payment_intent.succeeded","data":{"object":{"id":"pi_x"}}}'
    headers = {"stripe-signature": f"t={ts},v1={'0' * 64}"}

    try:
        adapter.verify_webhook(raw_body, headers)
        failures.append("Stripe bad signature should have raised SignatureError but did not")
    except SignatureError:
        pass
    except Exception as e:
        failures.append(f"Stripe bad sig raised wrong exception: {type(e).__name__}: {e}")


def _test_stripe_replay(failures: list[str]) -> None:
    """Old Stripe timestamp must raise ReplayError (self-consistency check)."""
    from core.payment.base import ReplayError, SignatureError
    from core.payment.stripe import StripeAdapter

    adapter = StripeAdapter(secret_key="sk_test_dummy", webhook_secret="whsec_dummy")
    old_ts = str(int(time.time()) - 400)  # outside ±300s window
    raw_body = b'{"type":"payment_intent.succeeded","data":{"object":{}}}'
    good_sig = _stripe_sign("whsec_dummy", old_ts, raw_body)
    headers = {"stripe-signature": f"t={old_ts},v1={good_sig}"}

    try:
        adapter.verify_webhook(raw_body, headers)
        failures.append("Stripe old timestamp should have raised ReplayError but did not")
    except ReplayError:
        pass
    except SignatureError:
        failures.append("Stripe old timestamp raised SignatureError instead of ReplayError")
    except Exception as e:
        failures.append(f"Stripe old timestamp raised wrong exception: {type(e).__name__}: {e}")


def _test_stripe_missing_headers(failures: list[str]) -> None:
    """Missing Stripe-Signature must raise SignatureError (not crash to 500)."""
    from core.payment.base import SignatureError
    from core.payment.stripe import StripeAdapter

    adapter = StripeAdapter(secret_key="sk_test_dummy", webhook_secret="whsec_dummy")
    raw_body = b'{"type":"payment_intent.succeeded"}'

    try:
        adapter.verify_webhook(raw_body, {})  # empty headers
        failures.append("Stripe missing headers should have raised SignatureError but did not")
    except SignatureError:
        pass
    except Exception as e:
        failures.append(f"Stripe missing headers raised wrong exception: {type(e).__name__}: {e}")


def _test_cors_not_wildcard(failures: list[str]) -> None:
    cors = os.environ.get("CORS_ORIGIN", "")
    if cors.strip() == "*":
        failures.append("CORS_ORIGIN must not be '*'")


def _test_debug_off(failures: list[str]) -> None:
    debug = os.environ.get("DEBUG", "false").lower()
    if debug in ("1", "true", "yes"):
        # Warning only — not a hard failure (dev may run with DEBUG=true)
        print("[Startup self-test] WARNING: DEBUG=true is unsafe in production", flush=True)
