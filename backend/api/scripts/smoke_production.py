from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse


CHECKS = [
    ("/healthz", "health", False, False),
    ("/readyz", "readiness", False, False),
    ("/api/v1/mobile/meta", "mobile api v1", False, False),
    ("/api/v1/mobile/products", "mobile products", False, True),
    ("/api/v1/mobile/categories", "mobile categories", False, True),
    ("/api/v1/mobile/announcements?placement=home", "mobile announcements", False, True),
]


def validated_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("La URL base debe usar http(s), por ejemplo https://fventas.cl")
    return base_url.rstrip("/")


def fetch_json(base_url: str, path: str, token: str = "") -> tuple[int, dict]:
    url = validated_base_url(base_url) + path
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=20) as response:  # nosec B310
        payload = response.read().decode("utf-8")
        return response.status, json.loads(payload or "{}")


def fetch_mobile_token(base_url: str) -> str:
    email = os.environ.get("FVENTAS_SMOKE_MOBILE_EMAIL", "").strip()
    password = os.environ.get("FVENTAS_SMOKE_MOBILE_PASSWORD", "").strip()
    if not email or not password:
        return ""

    url = validated_base_url(base_url) + "/api/v1/mobile/auth/login"
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:  # nosec B310
        payload = json.loads(response.read().decode("utf-8") or "{}")
        return payload.get("accessToken", "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run production smoke checks against FVENTAS Flask.")
    parser.add_argument("--base-url", default="http://localhost:5000")
    args = parser.parse_args()
    token = fetch_mobile_token(args.base_url)

    failures: list[str] = []
    print("FVENTAS Insights production smoke")
    print("-------------------------")
    for path, label, require_items, protected in CHECKS:
        try:
            status, payload = fetch_json(args.base_url, path, token if protected else "")
            ok = 200 <= status < 300
            items_count = len(payload.get("items", []))
            if require_items and items_count <= 0:
                ok = False
            marker = "OK" if ok else "FAIL"
            detail = payload.get("status") or f"{items_count} items"
            print(f"{marker} {label:<20} {status} {detail}")
            if not ok:
                failures.append(label)
        except HTTPError as exc:
            if protected and exc.code == 401 and not token:
                print(f"OK {label:<20} 401 token requerido")
                continue
            print(f"FAIL {label:<20} {exc}")
            failures.append(label)
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"FAIL {label:<20} {exc}")
            failures.append(label)

    if failures:
        print(f"Checks fallidos: {', '.join(failures)}")
        sys.exit(1)

    print("FVENTAS listo para recibir trafico.")


if __name__ == "__main__":
    main()
