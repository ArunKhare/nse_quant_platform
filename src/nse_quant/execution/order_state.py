"""Order-state transition rules."""

from __future__ import annotations

from nse_quant.core.models import OrderStatus

ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {
        OrderStatus.SUBMITTED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.FILLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.CANCELLED: set(),
}


class InvalidOrderTransitionError(ValueError):
    pass


def validate_transition(current: OrderStatus, next_status: OrderStatus) -> None:
    if next_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidOrderTransitionError(
            f"Invalid order transition: {current.value} -> {next_status.value}"
        )


def is_terminal(status: OrderStatus) -> bool:
    return not ALLOWED_TRANSITIONS.get(status, set())