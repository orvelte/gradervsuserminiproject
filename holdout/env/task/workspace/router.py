"""Support ticket router."""

TEAMS = ("billing", "accounts", "technical", "shipping", "feedback")


def route(ticket: dict) -> str:
    """Return the team that should handle `ticket` (keys: id, subject, body, customer_tier)."""
    return "technical"
