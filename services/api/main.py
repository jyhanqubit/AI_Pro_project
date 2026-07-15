"""API entry point: ``python -m services.api.main`` (backs ``make api``).

Serves the offline replay API on 127.0.0.1:8000 by default. Demo Mode needs no API key (section 3).
The bind host/port are overridable via ``SHOCKFLOW_API_HOST`` / ``SHOCKFLOW_API_PORT`` so the demo
can be opened from a phone on the same LAN (``make api-lan`` sets host=0.0.0.0). The safe default
stays loopback-only (section 16: demo defaults must be safe and offline-compatible).
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("SHOCKFLOW_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SHOCKFLOW_API_PORT", "8000"))
    uvicorn.run("services.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
