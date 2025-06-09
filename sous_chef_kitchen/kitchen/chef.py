"""
Field requests from the Sous Chef Kitchen API to the Prefect or Media Cloud
backends and cook up the results.
"""

import re
import os
from datetime import date, timedelta
from typing import Any, Dict, List
from uuid import UUID
import logging

import mediacloud.api
import prefect
from prefect.artifacts import Artifact
from prefect.blocks.system import Secret
from prefect.client.schemas.filters import (
    DeploymentFilter, DeploymentFilterName, FlowRunFilter, FlowRunFilterState,
    FlowRunFilterStateType, FlowRunFilterTags)
from prefect.client.schemas.objects import (
    FlowRun, StateType, WorkerStatus, WorkPoolStatus)
from prefect.exceptions import ObjectNotFound
from prefect.server.schemas.responses import SetStateStatus
from prefect.server.schemas.states import State
from sous_chef import SousChefRecipe

from sous_chef_kitchen.shared.models import (
    SousChefKitchenAuthStatus, SousChefKitchenSystemStatus)
from sous_chef_kitchen.shared.recipe import get_recipe_folder

BASE_TAGS = ["kitchen"]
DEFAULT_PREFECT_WORK_POOL = "bly" # TODO: Change this back to Guerin
PREFECT_ACTIVE_STATES = [StateType.RUNNING, StateType.SCHEDULED, StateType.PENDING]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")
PREFECT_WORK_POOL = os.getenv("SC_PREFECT_WORK_POOL", DEFAULT_PREFECT_WORK_POOL)
logger  = logging.getLogger(__name__)

async def _auth_media_cloud(auth_email:str, auth_key:str) -> bool:
    """Confirm the account has the necessary Media Cloud permissions.
    
    Note: This is temporary and will be replaced by more formal permissions
    when available. See the note under validate_auth() for further explanation.
    """

    mc_search = mediacloud.api.SearchApi(auth_key)

    try:
        auth_result = mc_search.story_list(
            "mediacloud",
            start_date = date.today(),
            end_date = date.today() - timedelta(1),
            expanded = True)
        logger.info(f"Auth result: {auth_result}")
    except RuntimeError:
        # TODO: Parse out the text of the runtime error for the "real" error
        return False
    else:
        return True


def _run_to_dict(run: FlowRun) -> Dict[str, Any]:
    """Serialize a Prefect run into a dictionary."""

    return {
        "id": run.id,
        "name": run.name,
        "parameters": run.parameters,
        "state_name": run.state_name,
        "state_type": run.state_type,
        "tags": run.tags
    }

def _artifact_to_dict(artifact: Artifact) -> Dict[str, Any]:
    """ Serialize a prefect Artifact into a dictionary """
    return {
        "type": artifact.type,
        "key": artifact.key,
        "data": artifact.data,
        "description": artifact.description
    }


async def fetch_all_runs(tags:List[str]=[]) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Kitchen runs from Prefect."""
    
    tags += BASE_TAGS
    tags_filter = FlowRunFilter(tags=FlowRunFilterTags(all_=tags))

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=tags_filter)
        return [_run_to_dict(run) for run in runs]


async def cancel_recipe_run(recipe_name:str, run_id:str,
    tags:List[str]=[]):
    """Cancel the specified run for the specified Sous Chef recipe."""

    tags += BASE_TAGS + [recipe_name]
    all_runs = {run["id"]:run for run in await fetch_all_runs(tags)}
    recipe_run = all_runs.get(run_id)
    
    if not recipe_run:
        raise ValueError(
            f"Unable to find a run {run_id} for recipe {recipe_name}.")

    async with prefect.get_client() as client:
        result = await client.set_flow_run_state(
            recipe_run["id"], State(type=StateType.CANCELLING))
    
    if result.status == SetStateStatus.ABORT:
        raise RuntimeError(
            f"Unable to cancel the flow run: {result.details.reason}")
    
    return result


async def fetch_active_runs(tags:List[str]=[]) -> List[Dict[str, Any]]:
    """Fetch any active or upcoming Sous Chef Kitchen runs from Prefect."""

    return await fetch_runs_by_state(tags, PREFECT_ACTIVE_STATES)


async def fetch_all_runs(tags:List[str]=[]) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Kitchen runs from Prefect."""
    
    tags += BASE_TAGS
    tags_filter = FlowRunFilter(tags=FlowRunFilterTags(all_=tags))

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=tags_filter)
        return [_run_to_dict(run) for run in runs]


async def fetch_paused_runs(tags:List[str]=[]) -> List[Dict[str, Any]]:
    """Fetch any paused Sous Chef Kitchen runs from Prefect."""

    return await fetch_runs_by_state(tags, [StateType.PAUSED])


async def fetch_run_by_id(run_id: UUID | str) -> Dict[str, Any]:
    """Fetch a specific Sous Chef Kitchen run from Prefect by its ID."""

    if type(run_id) is str:
        try:
            run_id = UUID(run_id)
        except:
            raise ValueError(
                f"Failed to parse the string as a UUID for {run_id}.")

    async with prefect.get_client() as client:
        run = await client.read_flow_run(run_id)
        return _run_to_dict(run)
    

async def fetch_runs_by_state(tags:List[str]=[],
    states:List[StateType]=[]) -> List[Dict[str, Any]]:
    """Fetch Sous Chef Kitchen runs that match the specified filters."""

    tags += BASE_TAGS
    states_filter = FlowRunFilter(
        state=FlowRunFilterState(type=FlowRunFilterStateType(
            any_=states)),
        tags=FlowRunFilterTags(all_=tags))

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=states_filter)
        return [_run_to_dict(run) for run in runs]


async def get_system_status() -> SousChefKitchenSystemStatus:
    """Check whether the Sous Chef backend systems are available and ready."""
	
    # If the request made it this far then the API itself is ready
    status = SousChefKitchenSystemStatus(
        connection_ready=True, kitchen_api_ready=True)
    
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
            work_pool_name=PREFECT_WORK_POOL)
        status.prefect_workers_ready = any(
            w.status == WorkerStatus.ONLINE for w in workers)
        
    return status


async def pause_recipe_run(recipe_name:str, run_id:str, tags:List[str]=[]) -> None:
    """Pause the specified run for the specified Sous Chef recipe."""

    tags += BASE_TAGS + [recipe_name]
    active_runs = {run["id"]:run for run in await fetch_active_runs(tags)}
    recipe_run = active_runs.get(run_id)
    
    if not recipe_run:
        raise ValueError(
            f"Unable to find an active run named {run_id} for recipe {recipe_name}.")

    await prefect.pause_flow_run(flow_run_id=recipe_run["id"])


async def resume_recipe_run(recipe_name:str, run_id:str, tags:List[str]=[]) -> None:
    """Resume the specified run for the specified Sous Chef recipe."""

    tags += BASE_TAGS + [recipe_name]
    paused_runs = {run["id"]:run for run in await fetch_paused_runs(tags)}
    recipe_run = paused_runs.get(run_id)
    
    if not recipe_run:
        raise ValueError(
            f"Unable to find a paused run named {run_id} for recipe {recipe_name}.")

    await prefect.resume_flow_run(flow_run_id=recipe_run["id"])


#Reconfiguring to construct the SousChefRecipe in this stage, validating before invoking prefect.
async def start_recipe(recipe_name:str, tags:List[str]=[], 
    parameters:Dict= {}) -> FlowRun:
    """Handle orders for the requested recipe from the Sous Chef Kitchen, using SousChef v2 Recipes."""
    print(parameters)

    recipe_folder = get_recipe_folder(recipe_name)
    recipe_location = os.path.join(recipe_folder, "recipe.yaml")
    try:
        recipe = SousChefRecipe(recipe_location, parameters)
    except Exception as e:
        expected = SousChefRecipe.get_param_schema(recipe_location)["properties"]
        raise ValueError(f"Error validating parameters for '{recipe_name}' with {parameters}: \n {e} \n Expected schema like: {expected}")

    tags += BASE_TAGS
    deployment_filter = DeploymentFilter(name=DeploymentFilterName(
        any_=[PREFECT_DEPLOYMENT]))

    active_runs = await fetch_active_runs(tags)
    if len(active_runs) > 0:
        raise RuntimeError("Cannot start a new recipe run whiile another run is active")

    final_params = recipe.get_params()

    parameters = {"recipe_name": recipe_name, "tags": tags, "parameters": final_params}
    async with prefect.get_client() as client:
        response = await client.read_deployments(deployment_filter=deployment_filter)
        run = await client.create_flow_run_from_deployment(
            response[0].id, parameters=parameters, tags=tags)
    
    return _run_to_dict(run)


async def recipe_schema(recipe_name: str) -> Dict:
    try:
        recipe_folder = get_recipe_folder(recipe_name)
    except ValueError:
        return None
    
    recipe_location = os.path.join(recipe_folder, "recipe.yaml")
    return SousChefRecipe.get_param_schema(recipe_location)["properties"]


async def store_credentials(auth_email:str, auth_key:str) -> Secret:
    """Store user credentials as a secret block in Prefect."""

    get_user_name = lambda email: re.sub("\W+", "", email.split("@")[0])
    block_name = f"{get_user_name(auth_email)}-mc-api-secret"
    
    async with prefect.get_client() as client:
        try:
            user_block = await client.read_block_document_by_name(
                name=block_name, block_type_slug="secret")
        except ObjectNotFound:
            user_block = None

        if not user_block:
            user_block = Secret(name=block_name, value=auth_key)
            await user_block.save(name=block_name)
    
    return user_block


async def validate_auth(auth_email: str, auth_key: str) \
    -> SousChefKitchenAuthStatus:
    """Check whether the API key is authorized for Media Cloud and Sous Chef.

    Note: This is temporary and will be replaced by more formal permissions
    when available. For now, certain calls are used as proxies to gauge the
    permissions available to the user.
    
    Media Cloud: A successful call to story_list() is used as an approximation
    to demonstrate that the user has the permissions needed to make use of
    Media Cloud within Sous Chef.
    
    Sous Chef: Successfully connecting to Prefect and fetching and/or storing
    credentials is enough to demonstrate that the user has the permissions
    needed to make use of Prefect for Sous Chef.
    """

    status = SousChefKitchenAuthStatus()
    if not auth_email or not auth_key:
        return status
    
    status.media_cloud_authorized = await _auth_media_cloud(auth_email, auth_key)
    status.sous_chef_authorized = bool(await store_credentials(auth_email, auth_key))

    return status


async def fetch_run_artifacts(run_id: str):
    """ Fetch all of the artifacts associated with a given run """

    id_filter = FlowRunFilter(tags=FlowRunFilterID(id=run.id))

    async with prefect.get_client() as client:
        artifacts = await client.read_artifacts(flow_run_filter=id_filter)
        return [_artifact_to_dict(artifact) for artifact in artifacts]


# TODO: Remove this check
if __name__ == "__main__":
    import asyncio
    asyncio.run(start_recipe(recipe_name="test_name", tags=['kitchen'], parameters={"hello": "world"}))
