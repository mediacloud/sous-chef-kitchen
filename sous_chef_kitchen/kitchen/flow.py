"""
Run (cook) flow requests on Prefect using the kitchen-base flow.

This is the execution layer that:
1. Executes flows from the flow registry
2. Formats outputs for artifacts
3. Filters restricted fields based on permissions
4. Creates Prefect artifacts
5. Fires webhook notifications on completion (if configured)
"""

import os
import re
from typing import Any, Dict, List

import prefect
from prefect import flow, get_run_logger
from prefect.artifacts import create_table_artifact
from prefect.context import FlowRunContext
from pydantic import BaseModel as PydanticBaseModel
from sous_chef import get_flow

from sous_chef_kitchen.kitchen.webhook import fire_webhook

# Import BaseArtifact for artifact detection
try:
    from sous_chef.artifacts import BaseArtifact
except ImportError:
    # Fallback if artifacts module not available
    BaseArtifact = None

# Import flows to trigger registration
try:
    from sous_chef.flows import *  # noqa: F403, F401 # This triggers @register_flow decorators
except ImportError:
    pass  # Flows may not be available in all environments

BASE_TAGS = ["kitchen"]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")


@flow(name=PREFECT_DEPLOYMENT, log_prints=True)
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
    5. Fires webhook notifications on completion (if webhook_url provided)
    """
    logger = get_run_logger()
    tags += BASE_TAGS + [recipe_name]

    # Get flow run context early for webhook
    flow_run_context = None
    flow_run_id = None
    try:
        flow_run_context = FlowRunContext.get()
        if flow_run_context and flow_run_context.flow_run:
            flow_run_id = flow_run_context.flow_run.id
            flow_run_name = flow_run_context.flow_run.dict().get("name")
        else:
            flow_run_name = "unknown"
    except Exception:
        flow_run_name = "unknown"

    # Extract webhook params before execution
    webhook_url = parameters.get("webhook_url")
    webhook_secret = parameters.get("webhook_secret")

    # Track execution state for webhook
    execution_success = False
    execution_error = None
    filtered_data = {}

    try:
        # Get flow from registry
        flow_meta = get_flow(recipe_name)
        if not flow_meta:
            raise ValueError(f"Flow '{recipe_name}' not found")

        flow_func = flow_meta.get("func")
        if not flow_func:
            raise ValueError(
                f"Flow '{recipe_name}' is missing required 'func' attribute"
            )
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
        _create_artifacts(filtered_data, flow_run_name)

        execution_success = True

    except Exception as e:
        execution_error = str(e)
        logger.error(f"Flow execution failed: {e}", exc_info=True)
        # Re-raise so Prefect marks run as FAILED
        raise

    finally:
        # Fire webhook in finally block so it always runs (success or failure)
        if webhook_url and flow_run_id:
            try:
                fire_webhook(
                    webhook_url=webhook_url,
                    webhook_secret=webhook_secret,
                    flow_run_id=flow_run_id,
                    recipe_name=recipe_name,
                    tags=tags,
                    parameters=parameters,
                    success=execution_success,
                    error=execution_error,
                    artifacts=filtered_data if execution_success else None,
                )
            except Exception as webhook_error:
                # Never fail the flow because webhook failed
                logger.warning(f"Webhook delivery failed (non-fatal): {webhook_error}")

    return filtered_data


def _format_flow_output(
    run_data: Any, flow_meta: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Format flow output for artifact creation.

    Converts raw return value to: {task_name: {data: ..., restricted: bool}}

    Flows can return either:
    - A FlowOutput model instance (Pydantic BaseModel with BaseArtifact fields)
    - A Dict[str, BaseArtifact] directly

    This function handles both cases and validates that all values are BaseArtifact instances.
    """
    if BaseArtifact is None:
        # If BaseArtifact is not available, fall back to legacy behavior
        if isinstance(run_data, dict):
            if all(isinstance(v, dict) and "data" in v for v in run_data.values()):
                return run_data
            formatted = {}
            for key, value in run_data.items():
                restricted = flow_meta.get("restricted_fields", {}).get(key, False)
                formatted[key] = {"data": value, "restricted": restricted}
            return formatted
        return {"result": {"data": run_data, "restricted": False}}

    # Handle FlowOutput model instances (Pydantic BaseModel)
    if isinstance(run_data, PydanticBaseModel):
        # Convert FlowOutput model to dict
        run_data = run_data.model_dump()

    # Validate that run_data is a dict
    if not isinstance(run_data, dict):
        raise TypeError(
            f"Flow must return Dict[str, BaseArtifact] or FlowOutput model, "
            f"got {type(run_data).__name__}"
        )

    # Validate that all values are BaseArtifact instances
    formatted = {}
    for key, value in run_data.items():
        if not isinstance(value, BaseArtifact):
            raise TypeError(
                f"Flow return value '{key}' must be a BaseArtifact instance, "
                f"got {type(value).__name__}"
            )
        # Determine if restricted (could come from flow metadata)
        restricted = flow_meta.get("restricted_fields", {}).get(key, False)
        formatted[key] = {"data": value, "restricted": restricted}

    return formatted


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
    """
    Create Prefect artifacts from formatted flow outputs.

    Flows must return Dict[str, BaseArtifact]. This function calls
    serialize_for_prefect() on each artifact to get the table and description,
    then creates Prefect table artifacts.
    """
    if BaseArtifact is None:
        # If BaseArtifact is not available, skip artifact creation
        return

    for task_name, output in formatted_data.items():
        key = re.sub("[^0-9a-zA-Z]+", "-", task_name.lower())
        artifact = output["data"]

        # Validate that we have a BaseArtifact instance
        if not isinstance(artifact, BaseArtifact):
            print(
                f"Warning! Skipping artifact creation for '{task_name}': "
                f"expected BaseArtifact, got {type(artifact).__name__}"
            )
            continue

        # Use artifact's own serialization method
        serialized = artifact.serialize_for_prefect()
        table = serialized["table"]
        description = serialized["description"]

        try:
            create_table_artifact(
                key=f"{flow_run_name}-{key}",
                table=table,
                description=description,
            )
        except Exception as e:
            print(f"Warning! Failed to create artifact '{key}': {e}. Continuing...")
