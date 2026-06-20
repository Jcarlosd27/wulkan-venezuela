from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, apply_inventory_transition, inventory_movements_for_order, order_release_block_reason


def build_store():
    product = {
        "id": "prod-payment-gate",
        "companyId": "company-fventas",
        "sku": "FV-TST-001",
        "title": "Producto Test",
        "stock": 5,
        "status": "active",
    }
    order = {
        "id": "ord-payment-gate",
        "orderId": "ord-payment-gate",
        "companyId": "company-fventas",
        "customerId": "client-payment-gate",
        "status": "preparing",
        "inventoryStatus": "reserved",
        "stockStatus": "reserved",
        "totalUsd": 100.0,
        "paidUsd": 0.0,
        "items": [
            {
                "productId": "prod-payment-gate",
                "sku": "FV-TST-001",
                "title": "Producto Test",
                "quantity": 2,
                "unitPriceUsd": 50.0,
                "lineTotalUsd": 100.0,
            }
        ],
    }
    return {
        "companies": [
            {"id": "company-fventas", "name": "FVENTAS"},
            {"id": "company-ajena", "name": "Empresa ajena"},
        ],
        "products": [product],
        "orders": [order],
        "credit_movements": [],
        "stock_movements": [],
    }, order, product


def main() -> None:
    app.config["TESTING"] = True
    with app.test_request_context("/"):
        store, order, product = build_store()
        assert order_release_block_reason(order, inventory_movements_for_order(store, order), store)
        assert apply_inventory_transition(store, order, "delivered") is False
        assert order["dispatchStatus"] == "payment_hold"
        assert order["stockStatus"] == "payment_hold"
        assert product["stock"] == 5

        store["credit_movements"].append(
            {
                "companyId": "company-ajena",
                "movementType": "payment",
                "orderId": "ord-payment-gate",
                "amountUsd": 100.0,
            }
        )
        assert order_release_block_reason(order, inventory_movements_for_order(store, order), store)
        assert apply_inventory_transition(store, order, "delivered") is False
        assert product["stock"] == 5

        store["credit_movements"].append(
            {
                "companyId": "company-fventas",
                "movementType": "payment",
                "orderId": "ord-payment-gate",
                "amountUsd": 100.0,
            }
        )
        assert order_release_block_reason(order, inventory_movements_for_order(store, order), store) == ""
        assert apply_inventory_transition(store, order, "delivered") is True
        assert order["inventoryStatus"] == "delivered"
        assert product["stock"] == 3

    print("ok - delivery is blocked until payment is complete")


if __name__ == "__main__":
    main()
