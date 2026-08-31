"""Billing stub — reserved for future implementation.

Currently disabled. Set MT_BILLING=1 to enable the stub.

Future design:
- Token-based billing (like old system) or credit-based
- Per-workflow pricing (base_cost + cost_per_step + cost_per_megapixel)
- Transaction history
- Admin token adjustment
"""

import os

BILLING_ENABLED = os.environ.get("MT_BILLING", "").strip().lower() in ("1", "true", "yes")


def calculate_cost(workflow_data: dict, user: dict = None) -> int:
    """Calculate token cost for a workflow execution.

    Currently returns 0 (free). Future implementation will:
    - Parse workflow nodes to estimate compute cost
    - Consider model size, steps, resolution
    - Apply user-specific discounts
    """
    if not BILLING_ENABLED:
        return 0
    # Stub: flat rate when enabled
    return 10


def check_balance(user: dict, cost: int) -> bool:
    """Check if user has enough balance. Always True when billing disabled."""
    if not BILLING_ENABLED:
        return True
    return user.get("token_balance", 0) >= cost


def deduct_balance(user_id: int, cost: int, description: str = "") -> bool:
    """Deduct tokens from user balance. No-op when billing disabled."""
    if not BILLING_ENABLED:
        return True
    # Future: implement actual deduction + transaction record
    return True


def get_transaction_history(user_id: int, limit: int = 50) -> list:
    """Get user transaction history. Empty when billing disabled."""
    if not BILLING_ENABLED:
        return []
    # Future: query transactions table
    return []
