"""API entry point: ``python -m services.api.main`` (backs ``make api``).

Serves the offline replay API on 127.0.0.1:8000. Demo Mode needs no API key (section 3).
"""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("services.api.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
