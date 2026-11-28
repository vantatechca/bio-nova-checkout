"""A pooled ``httpx.Client`` per outbound integration (Shopify, the client's payment API, ...).

Each caller keeps its own client (a different timeout, a different upstream), but all of them share this one
reason: reused across requests, a repeat call to the same host skips a fresh TCP/TLS handshake (keep-alive).
That's pure latency, never correctness -- each call is still an independent request.
"""

from __future__ import annotations

import httpx


def pooled_client(timeout_seconds: float) -> httpx.Client:
    # retries=1: httpx only retries a request that failed before any data was sent (e.g. the far end -- or a
    # proxy in between -- silently closed a pooled keep-alive connection during an idle period), so this is
    # still safe to retry even for a non-idempotent charge: nothing could have been received on the dead
    # connection in the first place. A request that actually reached the server and then failed is never retried.
    return httpx.Client(timeout=timeout_seconds, transport=httpx.HTTPTransport(retries=1))
