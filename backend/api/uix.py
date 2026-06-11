from __future__ import annotations


STATUS_BADGES = {
    "active": "text-bg-success",
    "prospect": "text-bg-info",
    "pending": "text-bg-warning",
    "inactive": "text-bg-secondary",
    "blocked": "text-bg-danger",
    "blocked_debt": "text-bg-danger",
    "blocked_credit": "text-bg-danger",
    "blocked_manual": "text-bg-danger",
    "suspended": "text-bg-warning",
    "none": "text-bg-secondary",
    "commercial_manager": "text-bg-primary",
    "sales": "text-bg-info",
    "payment_under_review": "text-bg-warning",
    "credit_review": "text-bg-warning",
    "approved_with_credit": "text-bg-success",
    "created": "text-bg-primary",
    "preparing": "text-bg-primary",
    "prepared": "text-bg-info",
    "ready": "text-bg-info",
    "in_route": "text-bg-primary",
    "dispatched": "text-bg-primary",
    "delivered": "text-bg-info",
    "failed": "text-bg-danger",
    "rescheduled": "text-bg-warning",
    "returned": "text-bg-dark",
    "partial_paid": "text-bg-warning",
    "paid": "text-bg-success",
    "cancelled": "text-bg-danger",
    "manual_review": "text-bg-warning",
    "credit_requested": "text-bg-warning",
    "review": "text-bg-warning",
    "rejected": "text-bg-danger",
    "approved": "text-bg-success",
    "blocked_limit": "text-bg-danger",
    "without_credit": "text-bg-secondary",
    "client_not_active": "text-bg-danger",
    "exhausted": "text-bg-danger",
    "in_use": "text-bg-primary",
    "available": "text-bg-success",
    "reserved": "text-bg-primary",
    "released": "text-bg-secondary",
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
    "current": "text-bg-success",
    "due_soon": "text-bg-warning",
    "overdue": "text-bg-danger",
    "in_management": "text-bg-primary",
    "promise": "text-bg-info",
    "uncollectible": "text-bg-dark",
    "closed": "text-bg-success",
    "without_due_date": "text-bg-secondary",
    "without_debt": "text-bg-success",
    "medium": "text-bg-warning",
    "high": "text-bg-danger",
    "critical": "text-bg-danger",
    "visible": "text-bg-success",
    "hidden": "text-bg-secondary",
    "replenishment": "text-bg-warning",
    "discontinued": "text-bg-dark",
}


def badge_class(status: str) -> str:
    return STATUS_BADGES.get(status, "text-bg-light")


def money_usd(value: float | int | str | None) -> str:
    amount = float(value or 0)
    return f"USD {amount:,.2f}"


def usd_to_ves(value: float | int | str | None, rate: float | int | str | None) -> str:
    amount = float(value or 0) * float(rate or 0)
    return f"VES {amount:,.2f}"
