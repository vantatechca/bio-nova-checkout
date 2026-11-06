"""Test doubles: an in-process SMTP server, an HTTP webhook receiver and a fake Shopify Storefront API and a fake client payment API."""

from __future__ import annotations

import base64
import email
import hashlib
import hmac
import json
import socketserver
import threading
import time
from dataclasses import dataclass, field
from email.message import Message
from http.server import BaseHTTPRequestHandler, HTTPServer


# ---------------------------------------------------------------- SMTP
@dataclass
class ReceivedMail:
    sender: str
    recipients: list[str]
    message: Message

    @property
    def subject(self) -> str:
        return str(self.message["Subject"])

    @property
    def body(self) -> str:
        return self.message.get_payload(decode=True).decode()


class FakeSmtpServer:
    """Minimal ESMTP server: EHLO, AUTH PLAIN / LOGIN, MAIL, RCPT, DATA. No TLS."""

    def __init__(self, user: str = "mailer", password: str = "secret") -> None:
        self.user, self.password = user, password
        self.mails: list[ReceivedMail] = []
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def reply(self, line: str) -> None:
                self.wfile.write(line.encode() + b"\r\n")

            def readline(self) -> str:
                return self.rfile.readline().decode().rstrip("\r\n")

            def check_login(self, user: str, password: str) -> None:
                self.reply(
                    "235 ok" if (user, password) == (outer.user, outer.password) else "535 5.7.8 bad credentials"
                )

            def handle(self) -> None:
                self.reply("220 fake ESMTP")
                sender, recipients = "", []
                while True:
                    line = self.readline()
                    if not line:
                        return
                    verb = line.split(" ", 1)[0].upper()
                    if verb == "EHLO":
                        self.reply("250-fake")
                        self.reply("250 AUTH PLAIN LOGIN")
                    elif verb == "AUTH":
                        parts = line.split()
                        if parts[1].upper() == "PLAIN":
                            raw = base64.b64decode(parts[2] if len(parts) > 2 else self._challenge("334 "))
                            _, user, password = raw.decode().split("\x00")
                            self.check_login(user, password)
                        else:  # LOGIN, with or without an initial response
                            user = base64.b64decode(
                                parts[2] if len(parts) > 2 else self._challenge("334 VXNlcm5hbWU6")
                            ).decode()
                            password = base64.b64decode(self._challenge("334 UGFzc3dvcmQ6")).decode()
                            self.check_login(user, password)
                    elif verb == "MAIL":
                        sender = line.split(":", 1)[1].strip().strip("<>")
                        self.reply("250 ok")
                    elif verb == "RCPT":
                        recipients.append(line.split(":", 1)[1].strip().strip("<>"))
                        self.reply("250 ok")
                    elif verb == "DATA":
                        self.reply("354 go ahead")
                        lines = []
                        while (data_line := self.rfile.readline().decode()) not in (".\r\n", ""):
                            lines.append(data_line)
                        message = email.message_from_string("".join(lines))
                        outer.mails.append(ReceivedMail(sender, list(recipients), message))
                        self.reply("250 queued")
                    elif verb == "QUIT":
                        self.reply("221 bye")
                        return
                    else:
                        self.reply("250 ok")

            def _challenge(self, prompt: str) -> str:
                self.reply(prompt)
                return self.readline()

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = Server(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# ---------------------------------------------------------------- webhook receiver
@dataclass
class ReceivedWebhook:
    headers: dict[str, str]
    body: bytes


@dataclass
class WebhookReceiver:
    """Records every POST; ``statuses`` is consumed one entry per request (default 200 afterwards)."""

    statuses: list[int] = field(default_factory=list)
    received: list[ReceivedWebhook] = field(default_factory=list)

    def __post_init__(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.received.append(ReceivedWebhook({k.lower(): v for k, v in self.headers.items()}, body))
                self.send_response(outer.statuses.pop(0) if outer.statuses else 200)
                self.end_headers()

            def log_message(self, *args) -> None:
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/hook"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# ---------------------------------------------------------------- fake Shopify Storefront API
class FakeShopify:
    """Speaks just enough of Shopify's Storefront GraphQL API: ``shop { name }`` and ``nodes(ids:)`` for variants."""

    TOKEN = "storefront-token"

    def __init__(self) -> None:
        self.variants: dict[int, dict] = {}  # variant id -> GraphQL node (without the id)
        self.force_status: int | None = None  # make every request fail with this status
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append(
                    {"path": self.path, "token": self.headers.get("X-Shopify-Storefront-Access-Token"), "body": body}
                )
                if outer.force_status:
                    return self._reply(outer.force_status, {})
                if self.headers.get("X-Shopify-Storefront-Access-Token") != outer.TOKEN:
                    return self._reply(401, {"errors": "Unauthorized"})
                if "shop {" in body.get("query", ""):
                    return self._reply(200, {"data": {"shop": {"name": "Fake Shop"}}})
                nodes = []
                for gid in body.get("variables", {}).get("ids", []):
                    vid = int(gid.rsplit("/", 1)[1])
                    nodes.append({"id": gid, **outer.variants[vid]} if vid in outer.variants else None)
                self._reply(200, {"data": {"nodes": nodes}})

            def _reply(self, status: int, payload: dict) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @staticmethod
    def variant(
        product: str,
        price: str,
        *,
        title: str = "Default Title",
        sku: str = "",
        available: bool = True,
        currency: str = "USD",
        image: str | None = "https://cdn.shopify.test/p.png",
    ) -> dict:
        return {
            "title": title,
            "sku": sku,
            "availableForSale": available,
            "price": {"amount": price, "currencyCode": currency},
            "image": {"url": image} if image else None,
            "product": {"title": product, "featuredImage": None},
        }

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# ---------------------------------------------------------------- fake *client* payment API (the card charge endpoint)
class FakeClientPaymentApi:
    """Plays the client's charge endpoint from docs/client-payment-api.md.

    It re-implements the signature check on its own (not by importing app code) so the contract itself is tested, and
    decides the outcome from the token: ``tok_mock_0002`` declines, ``tok_mock_500`` fails, anything else succeeds.
    The same Idempotency-Key always yields the same charge id.
    """

    def __init__(self) -> None:
        self.secret = ""
        self.requests: list[dict] = []
        self.charges: dict[str, str] = {}  # idempotency key -> charge id
        self.payment_page = ""  # redirect flow: the page URL to answer with (default: a valid https page)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
                timestamp = self.headers.get("X-Checkout-Timestamp", "0")
                expected = (
                    "sha256="
                    + hmac.new(outer.secret.encode(), f"{timestamp}.{raw}".encode(), hashlib.sha256).hexdigest()
                )
                fresh = abs(time.time() - int(timestamp or 0)) <= 300
                if not (fresh and hmac.compare_digest(expected, self.headers.get("X-Checkout-Signature", ""))):
                    return self._reply(401, {"error": "bad signature"})
                body = json.loads(raw)
                outer.requests.append(
                    {"body": body, "headers": {k.lower(): v for k, v in self.headers.items()}, "raw": raw}
                )
                if body.get("type") == "ping":
                    return self._reply(200, {"ok": True})
                if body.get("type") == "create_payment":  # redirect flow: hand back a hosted payment page
                    key = self.headers.get("Idempotency-Key", "")
                    page = outer.payment_page or f"https://pay.client.example/p/{key}"
                    return self._reply(200, {"status": "redirect", "redirect_url": page, "id": f"pay_{key[-6:]}"})
                token = body.get("token", "")
                if token == "tok_mock_0002":
                    return self._reply(200, {"status": "declined", "message": "Your card has insufficient funds."})
                if token == "tok_mock_500":
                    return self._reply(500, {"error": "processor down"})
                if token == "tok_mock_3ds":
                    return self._reply(200, {"status": "requires_action"})
                if token == "tok_mock_garbage":
                    return self._reply(200, "<html>oops</html>")
                key = self.headers.get("Idempotency-Key", "")
                charge_id = outer.charges.setdefault(key, f"ch_test_{len(outer.charges) + 1}")
                self._reply(200, {"status": "succeeded", "id": charge_id})

            def _reply(self, status: int, payload) -> None:
                data = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/charge"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def charge_requests(self) -> list[dict]:
        return [r for r in self.requests if r["body"].get("type") == "charge"]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
