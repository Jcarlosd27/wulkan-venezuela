from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CHECKS = [
    ("/healthz", "health"),
    ("/readyz", "readiness"),
    ("/api/mobile/products", "mobile products"),
    ("/api/mobile/categories", "mobile categories"),
    ("/api/mobile/announcements", "mobile announcements"),
]


def fetch_json(base_url: str, path: str) -> tuple[int, dict]:
    url = base_url.rstrip("/") + path
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
        return response.status, json.loads(payload or "{}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run production smoke checks against Wulkan Flask.")
    parser.add_argument("--base-url", default="http://localhost:5000")
    args = parser.parse_args()

    failures: list[str] = []
    print("Graphify production smoke")
    print("-------------------------")
    for path, label in CHECKS:
        try:
            status, payload = fetch_json(args.base_url, path)
            ok = 200 <= status < 300
            marker = "OK" if ok else "FAIL"
            detail = payload.get("status") or f"{len(payload.get('items', []))} items"
            print(f"{marker} {label:<20} {status} {detail}")
            if not ok:
                failures.append(label)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"FAIL {label:<20} {exc}")
            failures.append(label)

    if failures:
        print(f"Checks fallidos: {', '.join(failures)}")
        sys.exit(1)

    print("Wulkan listo para recibir trafico.")


if __name__ == "__main__":
    main()
