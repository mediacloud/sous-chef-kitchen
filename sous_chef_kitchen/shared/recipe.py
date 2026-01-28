"""
Work with Sous Chef flows via the flow registry.

This module provides backward-compatible functions that map to the new
flow registry system, replacing the old YAML recipe discovery.
"""

from typing import List, Tuple

from sous_chef import get_flow, list_flows


def get_recipe_names() -> List[str]:
    """Get list of available flow names (backward compat: 'recipe names')."""
    return list(list_flows().keys())


def get_recipe_info(flow_name: str) -> Tuple[str, List[str]]:
    """Get flow name and description (backward compat format).

    Returns tuple of (name, [description]) to match old YAML-based format.
    """
    flow = get_flow(flow_name)
    if not flow:
        raise ValueError(f"No flow found named {flow_name}.")
    description = flow.get("description") or flow.get("doc") or ""
    return (flow["name"], [description])
