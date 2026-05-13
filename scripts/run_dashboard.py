#!/usr/bin/env python3
"""Launch the Singular dashboard from a source checkout.

This helper mirrors `singular dashboard` for contributors who have not installed
console scripts yet.  It intentionally keeps only host/port parsing here and
reuses `singular.dashboard.run` for dependency checks and app creation.
"""

from __future__ import annotations

import argparse

from singular.dashboard import run


def main() -> None:
    """Parse dashboard launch options and start Uvicorn."""

    parser = argparse.ArgumentParser(description="Run the Singular web dashboard")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", default=8000, type=int, help="Bind port (default: 8000)"
    )
    args = parser.parse_args()
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
