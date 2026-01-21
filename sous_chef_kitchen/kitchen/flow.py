"""
Run (cook) flow requests on Prefect using the kitchen-base flow.

This is the execution layer that:
1. Executes flows from the flow registry
2. Formats outputs for artifacts
3. Filters restricted fields based on permissions
4. Creates Prefect artifacts
"""

import os
import re
from typing import Any, Dict, List

import pandas as pd
import prefect
from prefect import flow, get_run_logger
from prefect.artifacts import create_table_artifact
from prefect.context import FlowRunContext
from sous_chef import get_flow

# Import flows to trigger registration
try:
    from sous_chef.flows import *  # noqa: F403, F401 # This triggers @register_flow decorators
except ImportError:
    pass  # Flows may not be available in all environments

BASE_TAGS = ["kitchen"]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")


@flow(name=PREFECT_DEPLOYMENT)
def kitchen_base(
    recipe_name: str,
    tags: List[str] = [],
    parameters: Dict = {},
    return_restricted_artifacts: bool = False,
) -> Dict[str, Any]:
    """
    Execute a flow and handle output formatting/artifact creation.

    This is the execution layer that:
    1. Executes the flow from the registry
    2. Formats outputs for artifacts
    3. Filters restricted fields based on permissions
    4. Creates Prefect artifacts
    """
    logger = get_run_logger()
    tags += BASE_TAGS + [recipe_name]

    # Get flow from registry
    flow_meta = get_flow(recipe_name)
    if not flow_meta:
        raise ValueError(f"Flow '{recipe_name}' not found")

    flow_func = flow_meta["func"]
    params_model = flow_meta.get("params_model")

    # Validate and instantiate parameters
    if params_model:
        validated_params = params_model(**parameters)
    else:
        validated_params = parameters

    with prefect.tags(*tags):
        logger.info(f"Starting flow: {recipe_name}")

        # Execute flow - returns raw data
        run_data = flow_func(validated_params)

    # Format output for artifacts
    # Convert raw return value to artifact format: {task_name: {data: ..., restricted: bool}}
    formatted_data = _format_flow_output(run_data, flow_meta)

    # Filter restricted fields if user doesn't have permission
    filtered_data = _filter_restricted_fields(
        formatted_data, return_restricted=return_restricted_artifacts
    )

    # Create artifacts
    flow_run_name = FlowRunContext.get().flow_run.dict().get("name")
    _create_artifacts(filtered_data, flow_run_name)

    return filtered_data


def _format_flow_output(
    run_data: Any, flow_meta: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Format flow output for artifact creation.

    Converts raw return value to: {task_name: {data: ..., restricted: bool}}
    """
    # If already in correct format, return as-is
    if isinstance(run_data, dict):
        # Check if already formatted
        if all(isinstance(v, dict) and "data" in v for v in run_data.values()):
            return run_data

        # Otherwise, format it
        formatted = {}
        for key, value in run_data.items():
            # Determine if restricted (could come from flow metadata)
            restricted = flow_meta.get("restricted_fields", {}).get(key, False)
            formatted[key] = {"data": value, "restricted": restricted}
        return formatted

    # Single result - wrap it
    return {"result": {"data": run_data, "restricted": False}}


def _filter_restricted_fields(
    formatted_data: Dict[str, Dict[str, Any]], return_restricted: bool = False
) -> Dict[str, Dict[str, Any]]:
    """
    Filter restricted fields from output based on user permissions.

    This is business logic that MUST happen - flows can't skip it.
    """
    if return_restricted:
        return formatted_data

    # Filter out restricted artifacts
    filtered = {}
    for task_name, output in formatted_data.items():
        if not output.get("restricted", False):
            filtered[task_name] = output
        # If restricted and user doesn't have permission, skip it

    return filtered


def _create_artifacts(
    formatted_data: Dict[str, Dict[str, Any]], flow_run_name: str
) -> None:
    """Create Prefect artifacts from formatted flow outputs."""
    for task_name, output in formatted_data.items():
        key = re.sub("[^0-9a-zA-Z]+", "-", task_name.lower())
        data = output["data"]

        # Handle different data formats
        if isinstance(data, list):
            table = data
        elif isinstance(data, dict):
            table = [data]
        elif isinstance(data, pd.DataFrame):
            table = [data.to_json()]
        else:
            table = [{"value": data}]

        try:
            create_table_artifact(
                key=f"{flow_run_name}-{key}", table=table, description=task_name
            )
        except Exception as e:
            print(
                f"Warning! Failed to generate artifact: {key}. Error: {e}. continuing "
            )
