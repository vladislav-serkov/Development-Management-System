"""Prompt injection helper for user-defined rules."""

IMPORTANT_PREFIX_TEMPLATE = "IMPORTANT:\n{rules}\n\n"


def build_system_prompt(base: str, global_rules: str = "", project_rules: str = "") -> str:
    """Prepend global + project rules as IMPORTANT prefix to base system prompt.

    Order per D-10: global rules -> project rules -> base SYSTEM_PROMPT.
    Empty rules are skipped — no spurious IMPORTANT block if no rules set.
    """
    parts = [r.strip() for r in [global_rules, project_rules] if r and r.strip()]
    if not parts:
        return base
    combined_rules = "\n".join(parts)
    return IMPORTANT_PREFIX_TEMPLATE.format(rules=combined_rules) + base
