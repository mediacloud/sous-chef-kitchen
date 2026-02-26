"""
Field requests from the Sous Chef Kitchen API to the Prefect or Media Cloud
backends and cook up the results.
"""

import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

import mediacloud.api
import prefect
from prefect.artifacts import Artifact
from prefect.client.schemas.filters import (
    DeploymentFilter,
    DeploymentFilterName,
    FlowRunFilter,
    FlowRunFilterId,
    FlowRunFilterState,
    FlowRunFilterStateType,
    FlowRunFilterTags,
)
from prefect.client.schemas.objects import (
    FlowRun,
    StateType,
    WorkerStatus,
    WorkPoolStatus,
)
from prefect.exceptions import ObjectNotFound
from prefect.server.schemas.responses import SetStateStatus
from prefect.server.schemas.states import State
from pydantic import ValidationError
from sous_chef import get_flow, get_flow_schema, list_flows

from sous_chef_kitchen.kitchen.logging_config import setup_logging
from sous_chef_kitchen.shared.models import (
    SousChefKitchenAuthStatus,
    SousChefKitchenSystemStatus,
)
from sous_chef_kitchen.shared.recipe import get_recipe_info

# Import flows to trigger registration
try:
    from sous_chef.flows import *  # noqa: F403, F401 # This triggers @register_flow decorators
except ImportError:
    pass  # Flows may not be available in all environments

# Setup logging
setup_logging()

BASE_TAGS = ["kitchen"]
DEFAULT_PREFECT_WORK_POOL = "bly"
PREFECT_ACTIVE_STATES = [StateType.RUNNING, StateType.SCHEDULED, StateType.PENDING]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")
PREFECT_WORK_POOL = os.getenv("SC_PREFECT_WORK_POOL", DEFAULT_PREFECT_WORK_POOL)
MAX_USER_FLOWS = int(os.getenv("SC_MAX_USER_FLOWS", "1"))
logger = logging.getLogger("sous_chef_kitchen.chef")


def _run_to_dict(run: FlowRun) -> Dict[str, Any]:
    """Serialize a Prefect run into a dictionary."""

    return {
        "id": run.id,
        "name": run.name,
        "parameters": run.parameters,
        "state_name": run.state_name,
        "state_type": run.state_type,
        "tags": run.tags,
    }


def _artifact_to_dict(artifact: Artifact) -> Dict[str, Any]:
    """Serialize a prefect Artifact into a dictionary"""
    return {
        "type": artifact.type,
        "key": artifact.key,
        "data": artifact.data,
        "description": artifact.description,
    }


async def fetch_all_runs(
    tags: List[str] = [], parent_only: bool = True
) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Kitchen runs from Prefect.

    Args:
        tags: List of tags to filter runs by
        parent_only: If True, only return parent runs (exclude child/subflow runs). Defaults to True.
    """

    tags += BASE_TAGS
    tags_filter = FlowRunFilter(tags=FlowRunFilterTags(all_=tags))

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=tags_filter)

        # Filter out child runs if parent_only is True
        # Child runs (subflows) have parent_task_run_id set, parent runs have it as None
        if parent_only:
            runs = [
                run for run in runs if getattr(run, "parent_task_run_id", None) is None
            ]

        # Sort by most recent first (descending order) using the 'created' field
        runs = sorted(runs, key=lambda run: run.created, reverse=True)

        return [_run_to_dict(run) for run in runs]


async def cancel_recipe_run(
    recipe_name: str, run_id: str, tags: List[str] = []
) -> Dict[str, Any]:
    """Cancel the specified run for the specified Sous Chef recipe."""

    # Fetch the run directly by ID instead of filtering by tags
    try:
        run_dict = await fetch_run_by_id(run_id)
    except Exception as e:
        raise ValueError(
            f"Unable to find a run {run_id} for recipe {recipe_name}: {str(e)}"
        )

    # Verify the run has the required tags for authorization
    # If tags are provided (user's tag), verify the run has them
    # If no tags provided (admin viewing all runs), just verify it has BASE_TAGS
    required_tags = tags + BASE_TAGS if tags else BASE_TAGS
    run_tags = run_dict.get("tags", [])

    # Check if run has all required tags
    if not all(tag in run_tags for tag in required_tags):
        raise ValueError(
            f"Run {run_id} does not have the required tags. "
            f"Required: {required_tags}, Run has: {run_tags}"
        )

    async with prefect.get_client() as client:
        # Create state without state_details to avoid validation error
        cancel_state = State(type=StateType.CANCELLING, state_details=None)
        result = await client.set_flow_run_state(run_dict["id"], cancel_state)

    if result.status == SetStateStatus.ABORT:
        raise RuntimeError(f"Unable to cancel the flow run: {result.details.reason}")

    return result


async def fetch_active_runs(tags: List[str] = []) -> List[Dict[str, Any]]:
    """Fetch any active or upcoming Sous Chef Kitchen runs from Prefect."""

    return await fetch_runs_by_state(tags, PREFECT_ACTIVE_STATES)


async def fetch_paused_runs(tags: List[str] = []) -> List[Dict[str, Any]]:
    """Fetch any paused Sous Chef Kitchen runs from Prefect."""

    return await fetch_runs_by_state(tags, [StateType.PAUSED])


async def fetch_run_by_id(run_id: UUID | str) -> Dict[str, Any]:
    """Fetch a specific Sous Chef Kitchen run from Prefect by its ID."""

    if type(run_id) is str:
        try:
            run_id = UUID(run_id)
        except ValueError:
            raise ValueError(f"Failed to parse the string as a UUID for {run_id}.")

    async with prefect.get_client() as client:
        run = await client.read_flow_run(run_id)
        return _run_to_dict(run)


async def fetch_runs_by_state(
    tags: List[str] = [], states: List[StateType] = []
) -> List[Dict[str, Any]]:
    """Fetch Sous Chef Kitchen runs that match the specified filters."""

    tags += BASE_TAGS
    states_filter = FlowRunFilter(
        state=FlowRunFilterState(type=FlowRunFilterStateType(any_=states)),
        tags=FlowRunFilterTags(all_=tags),
    )

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=states_filter)
        return [_run_to_dict(run) for run in runs]


async def get_system_status() -> SousChefKitchenSystemStatus:
    """Check whether the Sous Chef backend systems are available and ready."""

    # If the request made it this far then the API itself is ready
    status = SousChefKitchenSystemStatus(
        connection_ready=True, kitchen_api_ready=True, max_user_flows=MAX_USER_FLOWS
    )

    # Check whether Prefect Cloud, Work Pool, and Workers are ready
    async with prefect.get_client() as client:
        response = await client.hello()
        status.prefect_cloud_ready = response.status_code == 200

        try:
            work_pool = await client.read_work_pool(PREFECT_WORK_POOL)
            status.prefect_work_pool_ready = work_pool.status == WorkPoolStatus.READY
        except ObjectNotFound:
            status.prefect_work_pool_ready = False

        workers = await client.read_workers_for_work_pool(
            work_pool_name=PREFECT_WORK_POOL
        )
        status.prefect_workers_ready = any(
            w.status == WorkerStatus.ONLINE for w in workers
        )

    return status


async def pause_recipe_run(recipe_name: str, run_id: str, tags: List[str] = []) -> None:
    """Pause the specified run for the specified Sous Chef recipe."""

    tags += BASE_TAGS  # + [recipe_name]
    active_runs = {run["id"]: run for run in await fetch_active_runs(tags)}
    recipe_run = active_runs.get(run_id)

    if not recipe_run:
        raise ValueError(
            f"Unable to find an active run named {run_id} for recipe {recipe_name}."
        )

    await prefect.pause_flow_run(flow_run_id=recipe_run["id"])


async def resume_recipe_run(
    recipe_name: str, run_id: str, tags: List[str] = []
) -> None:
    """Resume the specified run for the specified Sous Chef recipe."""

    tags += BASE_TAGS  # + [recipe_name]
    paused_runs = {run["id"]: run for run in await fetch_paused_runs(tags)}
    recipe_run = paused_runs.get(run_id)

    if not recipe_run:
        raise ValueError(
            f"Unable to find a paused run named {run_id} for recipe {recipe_name}."
        )

    await prefect.resume_flow_run(flow_run_id=recipe_run["id"])


async def start_recipe(
    recipe_name: str,
    tags: List[str] = [],
    parameters: Dict = {},
    user_full_text_authorized: bool = False,
    auth_email: Optional[str] = None,
    user_is_admin: bool = False,
) -> Dict[str, Any]:
    """Handle orders for the requested flow from the Sous Chef Kitchen, using the flow registry."""

    # Get flow from registry
    flow_meta = get_flow(recipe_name)
    if not flow_meta:
        raise ValueError(f"Flow '{recipe_name}' not found")

    # Enforce admin-only recipes
    if flow_meta.get("admin_only", False) and not user_is_admin:
        raise RuntimeError(f"Recipe '{recipe_name}' is restricted to admin users.")

    # Validate parameters using flow's params model
    params_model = flow_meta.get("params_model")
    if params_model:
        try:
            validated_params = params_model(**parameters)
            # Convert Pydantic model to dict for serialization
            if hasattr(validated_params, "model_dump"):
                final_params = validated_params.model_dump()
            elif hasattr(validated_params, "dict"):
                final_params = validated_params.dict()
            else:
                final_params = parameters
        except ValidationError as e:
            # Format Pydantic validation errors in a user-friendly way
            schema = get_flow_schema(recipe_name)
            error_messages = []
            field_errors = {}

            for error in e.errors():
                # Get field path (handles nested fields)
                field_path = " -> ".join(str(loc) for loc in error["loc"])
                error_msg = error["msg"]
                field_errors[field_path] = error_msg
                error_messages.append(f"{field_path}: {error_msg}")

            # Create a formatted error message
            formatted_errors = "\n".join(error_messages)
            raise ValueError(
                f"Parameter validation failed for '{recipe_name}':\n{formatted_errors}\n\nExpected schema: {schema}"
            )
        except Exception as e:
            schema = get_flow_schema(recipe_name)
            raise ValueError(
                f"Error validating parameters for '{recipe_name}' with {parameters}: \n {e} \n Expected schema: {schema}"
            )
    else:
        final_params = parameters

    # Inject authenticated user's email into email_to param if the flow supports it
    if auth_email and params_model:
        # Check if the params model has an email_to field
        if (
            hasattr(params_model, "model_fields")
            and "email_to" in params_model.model_fields
        ):
            email_list = final_params.get("email_to", [])
            # Ensure email_list is a list
            if not isinstance(email_list, list):
                email_list = [email_list] if email_list else []
            # Add authenticated user's email if not already present
            if auth_email not in email_list:
                email_list.append(auth_email)
                final_params["email_to"] = email_list
                logger.info(
                    f"Added authenticated user email '{auth_email}' to email_to parameter for recipe '{recipe_name}'"
                )
        # Also handle case where params_model might be a dict or have different structure
        elif isinstance(final_params, dict) and "email_to" in final_params:
            email_list = final_params.get("email_to", [])
            if not isinstance(email_list, list):
                email_list = [email_list] if email_list else []
            if auth_email not in email_list:
                email_list.append(auth_email)
                final_params["email_to"] = email_list
                logger.info(
                    f"Added authenticated user email '{auth_email}' to email_to parameter for recipe '{recipe_name}'"
                )

    tags += BASE_TAGS
    deployment_filter = DeploymentFilter(
        name=DeploymentFilterName(any_=[PREFECT_DEPLOYMENT])
    )

    active_runs = await fetch_active_runs(tags)
    if len(active_runs) >= MAX_USER_FLOWS:
        raise RuntimeError(
            f"Cannot start a new recipe run. You have {len(active_runs)}/{MAX_USER_FLOWS} allocated flows running. "
            "Please wait for your current runs to complete or cancel them before starting a new one."
        )

    prefect_parameters = {
        "recipe_name": recipe_name,
        "tags": tags,
        "parameters": final_params,
        "return_restricted_artifacts": user_full_text_authorized,
    }
    async with prefect.get_client() as client:
        response = await client.read_deployments(deployment_filter=deployment_filter)
        if not response:
            raise ValueError(
                f"No deployment found matching '{PREFECT_DEPLOYMENT}'. "
                "The deployment may not be registered in Prefect. "
                "Please check that the Prefect deployment exists and is available."
            )
        run = await client.create_flow_run_from_deployment(
            response[0].id, parameters=prefect_parameters, tags=tags
        )

    return _run_to_dict(run)


async def recipe_schema(recipe_name: str, is_admin: bool = False) -> Dict:
    """Get parameter schema for a flow."""
    flow_meta = get_flow(recipe_name)
    if not flow_meta:
        return {}

    # Enforce admin-only recipes
    if flow_meta.get("admin_only", False) and not is_admin:
        # Return empty dict to avoid leaking which recipes exist
        raise ValueError(f"Recipe '{recipe_name}' not found")

    schema = get_flow_schema(recipe_name)
    if not schema:
        return {}
    return schema  # Already returns properties dict


async def recipe_list(is_admin: bool = False) -> Dict:
    """List available flows from the flow registry."""
    logger.info("In Recipe List")
    try:
        flows = list_flows()
        recipe_info = {}
        for name in flows.keys():
            flow_meta = get_flow(name)
            # Filter out admin-only recipes for non-admin users
            if flow_meta and flow_meta.get("admin_only", False) and not is_admin:
                continue
            recipe_info[name] = get_recipe_info(name)
        logger.info(f"Got {len(recipe_info)} flows")
        return recipe_info
    except Exception as e:
        logger.error(f"Error getting recipe list: {e}")
        return {"recipes": [], "error": str(e)}


async def validate_auth(auth_email: str, auth_key: str) -> SousChefKitchenAuthStatus:
    """Check whether the API key is authorized for Media Cloud and Sous Chef.

    More Formal Permissions approach, ideally:
    Mediacloud API provides a user_profile method
    1. If the result not a 403, the user is mediacloud_authorized
    2. If the result has "full-text-access" in its groups, the user is media_cloud_full_text_authorized
    3. If the result has "sous-chef-user" in its groups, then then the user is sous_chef_authorized

    The situation in fact, given that the response type and groups are not set up in mc yet:
    1. If the result is not {"message": "User Not Found"}, the user is media_cloud_authorized
    2. If the result has "is_staff==True", the user is media_cloud_full_text_authorized
    3. If the user is media_cloud_authorized, the user is sous_chef_authorized
    """

    logger.info(f"Starting auth validation for email: {auth_email}")
    status = SousChefKitchenAuthStatus()

    if not auth_email or not auth_key:
        logger.warning(
            f"Missing auth credentials - email: {auth_email}, key present: {bool(auth_key)}"
        )
        return status

    try:
        logger.info(f"Creating MediaCloud SearchApi instance for {auth_email}")
        mc_search = mediacloud.api.SearchApi(auth_key)
        logger.info(f"Calling user_profile() for {auth_email}")
        auth_result = mc_search.user_profile()
        logger.info(f"MediaCloud API response for {auth_email}: {auth_result}")

        if "message" in auth_result and auth_result["message"] == "User Not Found":
            logger.warning(f"User not found for email: {auth_email}")
            return status

        status.media_cloud_authorized = True
        status.media_cloud_staff = auth_result.get("is_staff", False)
        status.media_cloud_full_text_authorized = auth_result.get("is_staff", False)
        status.sous_chef_authorized = True
        status.tag_slug = generate_tag_slug(auth_email, auth_key)

        logger.info(
            f"Auth successful for {auth_email}: "
            f"MC: {status.media_cloud_authorized}, "
            f"MC-FT: {status.media_cloud_full_text_authorized}, "
            f"SC: {status.sous_chef_authorized}, "
            f"Tag: {status.tag_slug}"
        )

    except Exception as e:
        logger.error(f"Error validating auth for {auth_email}: {str(e)}", exc_info=True)
        return status

    logger.info(f"Final auth status for {auth_email}: {status}")
    return status


def generate_tag_slug(user_email: str, api_key: str):
    # Sanitize the email for readability
    if "@" not in user_email:
        logger.warning(f"Invalid email format: {user_email}")
        base_slug = re.sub(r"[^a-zA-Z0-9]", "-", user_email.lower())
    else:
        base_slug = re.sub(r"[^a-zA-Z0-9]", "-", user_email.split("@")[0].lower())

    # Use part of a hash to ensure uniqueness
    digest = hashlib.sha1(f"{user_email}:{api_key}".encode()).hexdigest()[:8]

    # Join to create a tag-safe string
    tag = f"user-{base_slug}-{digest}"
    return tag


async def fetch_run_artifacts(run_id: str) -> List[Dict[str, Any]]:
    """Fetch artifacts for a specific run."""

    id_filter = FlowRunFilter(id=FlowRunFilterId(any_=[run_id]))

    async with prefect.get_client() as client:
        artifacts = await client.read_artifacts(flow_run_filter=id_filter)
        return [_artifact_to_dict(artifact) for artifact in artifacts]


# TODO: Remove this check
if __name__ == "__main__":
    import asyncio

    asyncio.run(
        start_recipe(
            recipe_name="test_name", tags=["kitchen"], parameters={"hello": "world"}
        )
    )
