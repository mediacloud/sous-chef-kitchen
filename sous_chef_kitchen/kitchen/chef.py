"""
Field requests from the Sous Chef Kitchen API to the Prefect or Media Cloud
backends and cook up the results.
"""

import logging
import os
import re
from datetime import date, timedelta
from typing import Any, Dict, List
from uuid import UUID
import hashlib

import mediacloud.api
import prefect
from prefect.artifacts import Artifact
from prefect.blocks.system import Secret
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
from sous_chef import SousChefRecipe

from sous_chef_kitchen.shared.models import (
    SousChefKitchenAuthStatus,
    SousChefKitchenSystemStatus,
)
from sous_chef_kitchen.shared.recipe import get_recipe_folder

BASE_TAGS = ["kitchen"]
DEFAULT_PREFECT_WORK_POOL = "bly"
PREFECT_ACTIVE_STATES = [StateType.RUNNING, StateType.SCHEDULED, StateType.PENDING]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")
PREFECT_WORK_POOL = os.getenv("SC_PREFECT_WORK_POOL", DEFAULT_PREFECT_WORK_POOL)
logger = logging.getLogger(__name__)


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


async def fetch_all_runs(tags: List[str] = []) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Kitchen runs from Prefect."""

    tags += BASE_TAGS
    tags_filter = FlowRunFilter(tags=FlowRunFilterTags(all_=tags))

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=tags_filter)
        return [_run_to_dict(run) for run in runs]


async def cancel_recipe_run(
    recipe_name: str, run_id: str, tags: List[str] = []
) -> Dict[str, Any]:
    """Cancel the specified run for the specified Sous Chef recipe."""

    tags += BASE_TAGS# + [recipe_name]
    all_runs = {run["id"]: run for run in await fetch_all_runs(tags)}
    recipe_run = all_runs.get(run_id)

    if not recipe_run:
        raise ValueError(f"Unable to find a run {run_id} for recipe {recipe_name}.")

    async with prefect.get_client() as client:
        result = await client.set_flow_run_state(
            recipe_run["id"], State(type=StateType.CANCELLING)
        )

    if result.status == SetStateStatus.ABORT:
        raise RuntimeError(f"Unable to cancel the flow run: {result.details.reason}")

    return result


async def fetch_active_runs(tags: List[str] = []) -> List[Dict[str, Any]]:
    """Fetch any active or upcoming Sous Chef Kitchen runs from Prefect."""

    return await fetch_runs_by_state(tags, PREFECT_ACTIVE_STATES)


async def fetch_all_runs(tags: List[str] = []) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Kitchen runs from Prefect."""

    tags += BASE_TAGS
    tags_filter = FlowRunFilter(tags=FlowRunFilterTags(all_=tags))

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=tags_filter)
        return [_run_to_dict(run) for run in runs]


async def fetch_paused_runs(tags: List[str] = []) -> List[Dict[str, Any]]:
    """Fetch any paused Sous Chef Kitchen runs from Prefect."""

    return await fetch_runs_by_state(tags, [StateType.PAUSED])


async def fetch_run_by_id(run_id: UUID | str) -> Dict[str, Any]:
    """Fetch a specific Sous Chef Kitchen run from Prefect by its ID."""

    if type(run_id) is str:
        try:
            run_id = UUID(run_id)
        except:
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
    status = SousChefKitchenSystemStatus(connection_ready=True, kitchen_api_ready=True)

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

    tags += BASE_TAGS# + [recipe_name]
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

    tags += BASE_TAGS# + [recipe_name]
    paused_runs = {run["id"]: run for run in await fetch_paused_runs(tags)}
    recipe_run = paused_runs.get(run_id)

    if not recipe_run:
        raise ValueError(
            f"Unable to find a paused run named {run_id} for recipe {recipe_name}."
        )

    await prefect.resume_flow_run(flow_run_id=recipe_run["id"])


# Reconfiguring to construct the SousChefRecipe in this stage, validating before invoking prefect.
async def start_recipe(
    recipe_name: str,
    tags: List[str] = [],
    parameters: Dict = {},
    user_full_text_authorized: bool = False,
) -> Dict[str, Any]:
    """Handle orders for the requested recipe from the Sous Chef Kitchen, using SousChef v2 Recipes."""
    print(parameters)

    recipe_folder = get_recipe_folder(recipe_name)
    recipe_location = os.path.join(recipe_folder, "recipe.yaml")
    try:
        recipe = SousChefRecipe(recipe_location, parameters)
    except Exception as e:
        expected = SousChefRecipe.get_param_schema(recipe_location)["properties"]
        raise ValueError(
            f"Error validating parameters for '{recipe_name}' with {parameters}: \n {e} \n Expected schema like: {expected}"
        )

    tags += BASE_TAGS
    deployment_filter = DeploymentFilter(
        name=DeploymentFilterName(any_=[PREFECT_DEPLOYMENT])
    )

    active_runs = await fetch_active_runs(tags)
    if len(active_runs) > 0:
        raise RuntimeError("Cannot start a new recipe run whiile another run is active")

    final_params = recipe.get_params()

    parameters = {
        "recipe_name": recipe_name,
        "tags": tags,
        "parameters": final_params,
        "return_restricted_artifacts": user_full_text_authorized,
    }
    async with prefect.get_client() as client:
        response = await client.read_deployments(deployment_filter=deployment_filter)
        run = await client.create_flow_run_from_deployment(
            response[0].id, parameters=parameters, tags=tags
        )

    return _run_to_dict(run)


async def recipe_schema(recipe_name: str) -> Dict:
    try:
        recipe_folder = get_recipe_folder(recipe_name)
    except ValueError:
        return None

    recipe_location = os.path.join(recipe_folder, "recipe.yaml")
    return SousChefRecipe.get_param_schema(recipe_location)["properties"]


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

    status = SousChefKitchenAuthStatus()
    if not auth_email or not auth_key:
        logger.warning("Missing auth credentials")
        return status

    try:
        mc_search = mediacloud.api.SearchApi(auth_key)
        auth_result = mc_search.user_profile()
        
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
            f"SC: {status.sous_chef_authorized}"
        )
        
    except Exception as e:
        logger.error(f"Error validating auth for {auth_email}: {str(e)}")
        return status

    return status


def generate_tag_slug(user_email:str, api_key:str):
    # Sanitize the email for readability
    base_slug = re.sub(r'[^a-zA-Z0-9]', '-', user_email.split('@')[0].lower())

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
