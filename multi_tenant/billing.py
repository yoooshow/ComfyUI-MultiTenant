"""Token cost calculation — flat rate only."""

# Default flat fee per execution. Change this to adjust pricing.
FLAT_FEE = 10


def calculate_cost(workflow_body: dict | None = None, user: dict | None = None) -> int:
    """Return the flat token cost per execution."""
    return FLAT_FEE
