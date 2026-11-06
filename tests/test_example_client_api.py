"""The reference client endpoint in examples/ must really follow docs/client-payment-api.md.

These tests drive it with requests signed exactly the way the checkout signs them (using the app's own ``sign``).
"""

import importlib.util
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.client_payment_api import sign

SECRET = "capi_example_secret"


@pytest.fixture
def example():
    path = Path(__file__).resolve().parent.parent / "examples" / "client_payment_api.py"
    spec = importlib.util.spec_from_file_location("client_payment_api_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SIGNING_SECRET = SECRET
    return TestClient(module.app)


def signed(payload, *, key="cs_1", secret=SECRET, timestamp=None):
    body = json.dumps(payload, separators=(",", ":"))
    ts = str(int(time.time()) if timestamp is None else timestamp)
    return {
        "content": body,
        "headers": {"X-Checkout-Timestamp": ts, "X-Checkout-Signature": sign(secret, ts, body), "Idempotency-Key": key},
    }


CHARGE = {"type": "charge", "reference": "cs_1", "amount": 5500, "currency": "USD", "token": "tok_mock_4242"}


def test_ping(example):
    assert example.post("/charge", **signed({"type": "ping"})).json() == {"ok": True}


def test_a_signed_charge_succeeds(example):
    response = example.post("/charge", **signed(CHARGE))
    assert (
        response.status_code == 200
        and response.json()["status"] == "succeeded"
        and response.json()["id"].startswith("ch_")
    )


def test_a_declined_card(example):
    response = example.post("/charge", **signed({**CHARGE, "token": "tok_mock_0002"}, key="cs_2"))
    assert response.json() == {"status": "declined", "message": "Your card has insufficient funds."}


def test_retries_with_the_same_idempotency_key_return_the_same_charge(example):
    first = example.post("/charge", **signed(CHARGE, key="cs_9")).json()
    second = example.post("/charge", **signed({**CHARGE, "token": "tok_mock_9999"}, key="cs_9")).json()
    assert first == second  # the second request did not charge anything


def test_wrong_secret_is_rejected(example):
    assert example.post("/charge", **signed(CHARGE, secret="not-the-secret")).status_code == 401


def test_tampered_body_is_rejected(example):
    request = signed(CHARGE)
    request["content"] = request["content"].replace("5500", "1")
    assert example.post("/charge", **request).status_code == 401


def test_old_timestamps_are_rejected_as_replays(example):
    assert example.post("/charge", **signed(CHARGE, timestamp=int(time.time()) - 3600)).status_code == 401


def test_missing_headers_are_rejected(example):
    assert example.post("/charge", content=json.dumps(CHARGE)).status_code == 401


def test_a_decline_is_not_remembered_so_another_card_can_be_tried_with_the_same_key(example):
    declined = example.post("/charge", **signed({**CHARGE, "token": "tok_mock_0002"}, key="cs_5")).json()
    paid = example.post("/charge", **signed({**CHARGE, "token": "tok_mock_4242"}, key="cs_5")).json()
    again = example.post("/charge", **signed({**CHARGE, "token": "tok_mock_7777"}, key="cs_5")).json()
    assert declined["status"] == "declined"
    assert paid["status"] == "succeeded" and again == paid  # once paid, any retry returns that same charge
