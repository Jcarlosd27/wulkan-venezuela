from __future__ import annotations

from typing import Any


def rotation_chart(products: list[dict[str, Any]]) -> dict[str, Any]:
    top_products = sorted(
        products,
        key=lambda product: int(product.get("rotationLast30Days") or 0),
        reverse=True,
    )[:8]

    return {
        "labels": [product["sku"] for product in top_products],
        "values": [int(product.get("rotationLast30Days") or 0) for product in top_products],
        "title": "Rotacion ultimos 30 dias",
    }


def stock_health(products: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "available": sum(1 for product in products if int(product.get("availableStock", product.get("stock", 0)) or 0) > 5),
        "low": sum(1 for product in products if 0 < int(product.get("availableStock", product.get("stock", 0)) or 0) <= 5),
        "out": sum(1 for product in products if int(product.get("availableStock", product.get("stock", 0)) or 0) <= 0),
    }
