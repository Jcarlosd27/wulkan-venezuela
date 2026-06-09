from __future__ import annotations


STATUS_BADGES = {
    "active": "text-bg-success",
    "pending": "text-bg-warning",
    "inactive": "text-bg-secondary",
    "blocked": "text-bg-danger",
    "suspended": "text-bg-warning",
    "commercial_manager": "text-bg-primary",
    "sales": "text-bg-info",
    "payment_under_review": "text-bg-warning",
    "credit_review": "text-bg-warning",
    "approved_with_credit": "text-bg-success",
    "created": "text-bg-primary",
    "preparing": "text-bg-primary",
    "delivered": "text-bg-info",
    "partial_paid": "text-bg-warning",
    "paid": "text-bg-success",
    "cancelled": "text-bg-danger",
    "manual_review": "text-bg-warning",
    "credit_requested": "text-bg-warning",
    "rejected": "text-bg-danger",
    "approved": "text-bg-success",
    "released": "text-bg-success",
    "without_credit": "text-bg-secondary",
    "client_not_active": "text-bg-danger",
    "exhausted": "text-bg-danger",
    "in_use": "text-bg-primary",
    "available": "text-bg-success",
    "reserved": "text-bg-primary",
    "delivered": "text-bg-info",
    "released": "text-bg-secondary",
    "pending": "text-bg-light",
    "review": "text-bg-warning",
    "insufficient_stock": "text-bg-danger",
    "low": "text-bg-warning",
    "out": "text-bg-danger",
    "cash": "text-bg-success",
    "term_credit": "text-bg-warning",
    "credit_line": "text-bg-primary",
    "phone_request": "text-bg-info",
    "commission_pending": "text-bg-warning",
    "commission_approved": "text-bg-success",
    "commission_paid": "text-bg-primary",
    "commission_cancelled": "text-bg-danger",
    "visible": "text-bg-success",
    "hidden": "text-bg-secondary",
}


def badge_class(status: str) -> str:
    return STATUS_BADGES.get(status, "text-bg-light")


def money_usd(value: float | int | str | None) -> str:
    amount = float(value or 0)
    return f"USD {amount:,.2f}"


def usd_to_ves(value: float | int | str | None, rate: float | int | str | None) -> str:
    amount = float(value or 0) * float(rate or 0)
    return f"VES {amount:,.2f}"
