from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import resource
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as FVENTAS_app
from store import DEFAULT_COMPANY_ID, SAAS_PLAN_ID, SAAS_PLAN_NAME, SAAS_PLAN_PRICE_CLP, utc_now


def rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return usage / (1024 * 1024)
    return usage / 1024


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percent / 100) * (len(ordered) - 1))))
    return ordered[index]


def safe_mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def synthetic_store(
    *,
    users: int,
    products_count: int,
    orders_count: int,
) -> dict[str, Any]:
    now = utc_now()
    sellers_count = max(1, round(users * 0.16))
    admins_count = max(1, round(users * 0.03))
    clients_count = max(1, users - sellers_count - admins_count)
    categories_count = max(8, min(40, products_count // 12 or 8))

    categories = [
        {
            "id": f"cat-load-{index}",
            "companyId": DEFAULT_COMPANY_ID,
            "name": f"Categoria carga {index}",
            "slug": f"categoria-carga-{index}",
            "description": "Categoria sintetica para prueba de consumo.",
            "status": "active",
            "visibleInApp": True,
            "sortOrder": index,
            "createdAt": now,
            "updatedAt": now,
        }
        for index in range(categories_count)
    ]

    products = []
    for index in range(products_count):
        category = categories[index % len(categories)]
        price = 12 + (index % 900) * 1.7
        b2b_price = round(price * 0.88, 2)
        products.append(
            {
                "id": f"prod-load-{index}",
                "companyId": DEFAULT_COMPANY_ID,
                "sku": f"LOAD-{index:05d}",
                "title": f"Producto de carga {index}",
                "description": "Producto sintetico publicado para app movil y admin.",
                "shortDescription": "Producto sintetico.",
                "categoryId": category["id"],
                "categoryName": category["name"],
                "publicPriceUsd": round(price, 2),
                "originalPriceUsd": round(price * 1.08, 2),
                "b2bPriceUsd": b2b_price,
                "status": "active",
                "visibleInApp": True,
                "featured": index % 7 == 0,
                "onSale": index % 11 == 0,
                "discountPercent": 12 if index % 11 == 0 else 0,
                "requiresQuote": False,
                "requiresTechnicalValidation": index % 31 == 0,
                "imageUrl": "/static/uploads/catalog/fventas-product.svg",
                "imageUrls": ["/static/uploads/catalog/fventas-product.svg"],
                "pdfUrls": [],
                "variants": [],
                "specifications": {"familia": category["name"], "carga": "simulada"},
                "stock": 15 + index % 80,
                "physicalStock": 15 + index % 80,
                "availableStock": 15 + index % 80,
                "committedStock": index % 5,
                "createdAt": now,
                "updatedAt": now,
            }
        )

    admin_users = []
    for index in range(sellers_count):
        admin_users.append(
            {
                "id": f"seller-load-{index}",
                "companyId": DEFAULT_COMPANY_ID,
                "name": f"Vendedor carga {index}",
                "email": f"seller.load.{index}@fventas.test",
                "passwordHash": "not-used-in-load",
                "role": "sales",
                "status": "active",
                "sessionVersion": 0,
                "mobileAccessEnabled": True,
                "commissionRatePercent": 5 + (index % 5),
                "salesGoalUsd": 25000,
                "createdAt": now,
                "updatedAt": now,
            }
        )
    for index in range(admins_count):
        admin_users.append(
            {
                "id": f"admin-load-{index}",
                "companyId": DEFAULT_COMPANY_ID,
                "name": f"Admin carga {index}",
                "email": f"admin.load.{index}@fventas.test",
                "passwordHash": "not-used-in-load",
                "role": "super_admin",
                "status": "active",
                "sessionVersion": 0,
                "mobileAccessEnabled": True,
                "createdAt": now,
                "updatedAt": now,
            }
        )

    clients = []
    for index in range(clients_count):
        seller = admin_users[index % sellers_count]
        clients.append(
            {
                "id": f"client-load-{index}",
                "companyId": DEFAULT_COMPANY_ID,
                "businessName": f"Cliente carga {index}",
                "legalName": f"Cliente carga {index} SpA",
                "commercialName": f"Cliente carga {index}",
                "email": f"client.load.{index}@fventas.test",
                "passwordHash": "not-used-in-load",
                "status": "active",
                "clientType": "b2b",
                "clientCategory": "standard",
                "taxId": f"76.{index:03d}.{index % 900:03d}-{index % 10}",
                "phone": "+56 9 1000 0000",
                "address": "Direccion simulada",
                "city": "Santiago",
                "state": "Metropolitana",
                "country": "CL",
                "assignedSellerId": seller["id"],
                "assignedSellerName": seller["name"],
                "creditEnabled": True,
                "creditLimitUsd": 20000,
                "creditUsedUsd": 0,
                "paymentTermsDays": 30,
                "allowedPaymentTermsDays": [0, 15, 30],
                "defaultSaleType": "term_credit",
                "collectionStatus": "without_debt",
                "creditRiskLevel": "low",
                "mobileSessionVersion": 0,
                "mobileAccessEnabled": True,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            }
        )

    orders = []
    for index in range(orders_count):
        client = clients[index % len(clients)]
        seller_id = client.get("assignedSellerId", "")
        seller_name = client.get("assignedSellerName", "")
        product = products[index % len(products)]
        quantity = 1 + index % 4
        unit_price = float(product["b2bPriceUsd"])
        total_usd = round(unit_price * quantity, 2)
        balance_usd = total_usd if index % 3 else 0
        status = "approved_with_credit" if index % 4 else "payment_under_review"
        orders.append(
            {
                "id": f"order-load-{index}",
                "companyId": DEFAULT_COMPANY_ID,
                "orderId": f"order-load-{index}",
                "customerId": client["id"],
                "customerName": client["businessName"],
                "customer": {
                    "id": client["id"],
                    "name": client["businessName"],
                    "businessName": client["businessName"],
                    "sellerId": seller_id,
                    "sellerName": seller_name,
                },
                "sellerId": seller_id,
                "sellerName": seller_name,
                "items": [
                    {
                        "productId": product["id"],
                        "sku": product["sku"],
                        "title": product["title"],
                        "quantity": quantity,
                        "unitPriceUsd": unit_price,
                        "lineTotalUsd": total_usd,
                    }
                ],
                "grossUsd": total_usd,
                "netUsd": total_usd,
                "totalUsd": total_usd,
                "paidUsd": round(total_usd - balance_usd, 2),
                "balanceUsd": balance_usd,
                "saleType": "term_credit",
                "paymentTermDays": 30,
                "dueDate": "",
                "status": status,
                "creditStatus": "approved",
                "paymentStatus": "pending" if balance_usd else "paid",
                "dispatchStatus": "pending",
                "commissionRatePercent": 5,
                "commissionUsd": round(total_usd * 0.05, 2),
                "commissionStatus": "commission_pending",
                "createdAt": now,
                "updatedAt": now,
            }
        )

    return {
        "companies": [
            {
                "id": DEFAULT_COMPANY_ID,
                "name": "FVENTAS carga",
                "legalName": "FVENTAS carga",
                "country": "CL",
                "currency": "CLP",
                "baseCurrency": "USD",
                "exchangeRateBaseToLocal": 950,
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "subscriptions": [
            {
                "id": f"sub-{DEFAULT_COMPANY_ID}",
                "companyId": DEFAULT_COMPANY_ID,
                "planId": SAAS_PLAN_ID,
                "planName": SAAS_PLAN_NAME,
                "priceClp": SAAS_PLAN_PRICE_CLP,
                "billingCycle": "monthly",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "business_settings": {
            "marketCountry": "CL",
            "salesCurrency": "USD",
            "localCurrency": "CLP",
            "exchangeRateBaseToLocal": 950,
            "defaultPaymentTermsDays": [0, 15, 30],
            "purchaseConditionsScope": "Solo datos de tu empresa",
        },
        "categories": categories,
        "products": products,
        "clients": clients,
        "admin_users": admin_users,
        "orders": orders,
        "quotes": [],
        "credit_movements": [],
        "stock_movements": [],
        "announcements": [],
        "notifications": [],
        "media_assets": [],
        "service_technicians": [],
        "crm_records": [],
        "audit_events": [],
        "mobile_write_rate_events": [],
    }


def configure_app(state: dict[str, Any]) -> None:
    FVENTAS_app.load_store = lambda: state
    FVENTAS_app.save_store = lambda store: None
    FVENTAS_app.app.config.update(
        TESTING=True,
        SECRET_KEY="load-capacity-simulation-secret",
        DATA_BACKEND="sql",
        STORAGE_BACKEND="s3",
        REQUIRE_MOBILE_TOKEN=True,
        REJECT_LEGACY_MOBILE_TOKENS=True,
        REQUIRE_MOBILE_DEVICE_HEADER=True,
        ALLOW_LEGACY_MOBILE_API=False,
        WTF_CSRF_ENABLED=False,
    )


def mobile_headers(token: str, device_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-FVENTAS-Device-Id": device_id,
    }


ADMIN_USER_AGENT = "FVENTAS-load-admin/1.0"
ADMIN_DEVICE_HASH = hashlib.sha256(f"{ADMIN_USER_AGENT}|".encode("utf-8")).hexdigest()[:32]


def build_personas(state: dict[str, Any]) -> list[dict[str, str]]:
    personas: list[dict[str, str]] = []
    for index, client in enumerate(state["clients"]):
        device_id = f"load-client-device-{index}"
        token = FVENTAS_app.issue_mobile_token(client, device_id=device_id)
        personas.append(
            {
                "kind": "client",
                "id": client["id"],
                "token": token,
                "deviceId": device_id,
            }
        )
    for index, user in enumerate(
        item for item in state["admin_users"] if item.get("role") == "sales"
    ):
        device_id = f"load-seller-device-{index}"
        token = FVENTAS_app.issue_mobile_admin_token(user, device_id=device_id)
        personas.append(
            {
                "kind": "seller",
                "id": user["id"],
                "token": token,
                "deviceId": device_id,
            }
        )
    for user in (item for item in state["admin_users"] if item.get("role") == "super_admin"):
        personas.append({"kind": "admin", "id": user["id"], "token": "", "deviceId": ""})
    return personas


def request_path(persona: dict[str, str], product_ids: list[str], rng: random.Random) -> str:
    if persona["kind"] == "client":
        return rng.choice(
            [
                "/api/v1/mobile/meta",
                "/api/v1/mobile/home",
                "/api/v1/mobile/products?limit=24",
                f"/api/v1/mobile/products/{rng.choice(product_ids)}",
                "/api/v1/mobile/credit",
                "/api/v1/mobile/orders?limit=10",
                "/api/v1/mobile/profile",
            ]
        )
    if persona["kind"] == "seller":
        return rng.choice(
            [
                "/api/v1/mobile/seller/summary",
                "/api/v1/mobile/products?limit=24",
                "/api/v1/mobile/seller/clients?limit=20",
                "/api/v1/mobile/seller/orders?limit=20",
                "/api/v1/mobile/seller/commissions?limit=20",
            ]
        )
    return rng.choice(["/dashboard", "/products", "/clients", "/orders", "/credit", "/settings"])


def perform_request(persona: dict[str, str], path: str) -> dict[str, Any]:
    started = time.perf_counter()
    status = 0
    size = 0
    error = ""
    try:
        with FVENTAS_app.app.test_client() as client:
            if persona["kind"] == "admin":
                now_epoch = int(time.time())
                session_id = f"load-session-{persona['id']}"
                with client.session_transaction() as session:
                    session["admin_authenticated"] = True
                    session["admin_user_id"] = persona["id"]
                    session["admin_role"] = "super_admin"
                    session["admin_name"] = "Admin carga"
                    session["company_id"] = DEFAULT_COMPANY_ID
                    session["admin_session_version"] = 0
                    session["admin_session_id"] = session_id
                    session["admin_login_at"] = now_epoch
                    session["admin_last_seen_at"] = now_epoch
                    session["admin_device_hash"] = ADMIN_DEVICE_HASH
                    session["admin_ip_address"] = "127.0.0.1"
                response = client.get(path, headers={"User-Agent": ADMIN_USER_AGENT})
            else:
                response = client.get(
                    path,
                    headers=mobile_headers(persona["token"], persona["deviceId"]),
                )
            status = response.status_code
            size = len(response.get_data() or b"")
    except Exception as exc:  # pragma: no cover - this script reports failures.
        error = repr(exc)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "kind": persona["kind"],
        "path": path.split("?")[0],
        "status": status,
        "bytes": size,
        "elapsedMs": elapsed_ms,
        "error": error,
    }


def run_simulation(args: argparse.Namespace) -> dict[str, Any]:
    state = synthetic_store(
        users=args.users,
        products_count=args.products,
        orders_count=args.orders,
    )
    configure_app(state)
    personas = build_personas(state)
    product_ids = [item["id"] for item in state["products"]]
    rng = random.Random(args.seed)
    tasks = []
    for persona in personas:
        for _ in range(args.ops_per_user):
            tasks.append((persona, request_path(persona, product_ids, rng)))
    rng.shuffle(tasks)

    rss_start = rss_mb()
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(perform_request, persona, path) for persona, path in tasks]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    elapsed_seconds = time.perf_counter() - started
    rss_end = rss_mb()

    latencies = [float(item["elapsedMs"]) for item in results]
    status_counter = Counter(str(item["status"]) for item in results)
    kind_counter = Counter(item["kind"] for item in results)
    error_counter = Counter(item["error"] for item in results if item["error"])
    endpoint_data: dict[str, list[float]] = defaultdict(list)
    for item in results:
        endpoint_data[f"{item['kind']} {item['path']}"].append(float(item["elapsedMs"]))

    store_bytes = len(json.dumps(state, ensure_ascii=False, default=str).encode("utf-8"))
    response_bytes = sum(int(item["bytes"]) for item in results)
    logical_store_read_bytes = store_bytes * len(results)
    endpoint_summary = []
    for endpoint, endpoint_latencies in sorted(endpoint_data.items()):
        endpoint_summary.append(
            {
                "endpoint": endpoint,
                "requests": len(endpoint_latencies),
                "avgMs": round(safe_mean(endpoint_latencies), 2),
                "p95Ms": round(percentile(endpoint_latencies, 95), 2),
                "maxMs": round(max(endpoint_latencies), 2),
            }
        )

    return {
        "input": {
            "users": args.users,
            "personas": dict(kind_counter),
            "products": len(state["products"]),
            "orders": len(state["orders"]),
            "operations": len(results),
            "opsPerUser": args.ops_per_user,
            "workers": args.workers,
        },
        "dataset": {
            "jsonStoreMb": round(store_bytes / (1024 * 1024), 2),
            "logicalStoreReadGb": round(logical_store_read_bytes / (1024**3), 2),
        },
        "runtime": {
            "elapsedSeconds": round(elapsed_seconds, 2),
            "requestsPerSecond": round(len(results) / elapsed_seconds, 2) if elapsed_seconds else 0,
            "rssStartMb": round(rss_start, 2),
            "rssPeakMb": round(rss_end, 2),
            "rssDeltaMb": round(max(0, rss_end - rss_start), 2),
        },
        "latency": {
            "avgMs": round(safe_mean(latencies), 2),
            "p50Ms": round(percentile(latencies, 50), 2),
            "p95Ms": round(percentile(latencies, 95), 2),
            "p99Ms": round(percentile(latencies, 99), 2),
            "maxMs": round(max(latencies), 2) if latencies else 0,
        },
        "network": {
            "responseMb": round(response_bytes / (1024 * 1024), 2),
            "avgResponseKb": round((response_bytes / max(1, len(results))) / 1024, 2),
        },
        "statuses": dict(status_counter),
        "errors": dict(error_counter),
        "endpoints": endpoint_summary,
    }


def print_report(report: dict[str, Any]) -> None:
    print("FVENTAS capacity simulation")
    print("---------------------------")
    print(json.dumps({key: report[key] for key in ("input", "dataset", "runtime", "latency", "network", "statuses", "errors")}, indent=2, ensure_ascii=False))
    print("\nEndpoints:")
    for row in report["endpoints"]:
        print(
            f"- {row['endpoint']}: {row['requests']} req, "
            f"avg {row['avgMs']} ms, p95 {row['p95Ms']} ms, max {row['maxMs']} ms"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simula consumo de FVENTAS con usuarios moviles y panel admin sobre un store sintetico.",
    )
    parser.add_argument("--users", type=int, default=1500)
    parser.add_argument("--ops-per-user", type=int, default=3)
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--products", type=int, default=500)
    parser.add_argument("--orders", type=int, default=6000)
    parser.add_argument("--seed", type=int, default=20260618)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_simulation(args)
    print_report(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReporte JSON: {args.json_output}")
    failed = sum(count for status, count in report["statuses"].items() if not status.startswith(("2", "3")))
    return 1 if failed or report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
