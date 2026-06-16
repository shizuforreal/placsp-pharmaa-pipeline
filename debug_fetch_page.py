"""
Quick helper: fetch one PLACSP detail page and save its raw HTML to disk,
so you can inspect it in VS Code or send it back to Claude for debugging.

Usage:
    python debug_fetch_page.py "<the full URL>"

Saves to debug_page.html in the current folder and prints how many
characters were fetched.
"""

from __future__ import annotations

import sys

from pipeline.http_client import PoliteSession


def main() -> None:
    if len(sys.argv) != 2:
        print('Usage: python debug_fetch_page.py "<url>"')
        sys.exit(1)

    url = sys.argv[1]
    session = PoliteSession()
    response = session.get(url)

    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(response.text)

    print(f"Saved {len(response.text)} characters to debug_page.html")
    print(f"Status code: {response.status_code}")


if __name__ == "__main__":
    main()
