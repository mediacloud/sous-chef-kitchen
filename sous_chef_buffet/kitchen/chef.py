"""
Field requests from the Sous Chef Kitchen API to the Prefect or Media Cloud
backends and cook up the results.
"""

import re
import os
from datetime import date, timedelta
from typing import Any, Dict, List
from uuid import UUID

import mediacloud.api
import prefect
from prefect import flow
from prefect.blocks.system import Secret
from prefect.client.schemas.filters import (
    DeploymentFilter, DeploymentFilterName, FlowRunFilter, FlowRunFilterState,
    FlowRunFilterStateType, FlowRunFilterTags)
from prefect.client.schemas.objects import (
    FlowRun, StateType, WorkerStatus, WorkPoolStatus)
from prefect.exceptions import ObjectNotFound

from sous_chef import RunPipeline, recipe_loader

from sous_chef_buffet.shared import recipe
from sous_chef_buffet.shared.models import (
    SousChefKitchenAuthStatus, SousChefBaseOrder, SousChefKitchenSystemStatus)

DEFAULT_TAGS = ["buffet"]
DEFAULT_PREFECT_WORK_POOL = "Guerin"
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "buffet-base")
PREFECT_WORK_POOL = os.getenv("SC_PREFECT_WORK_POOL", DEFAULT_PREFECT_WORK_POOL)


async def _auth_media_cloud(auth_email:str, auth_key:str) -> bool:
    """Confirm the account has the necessary Media Cloud permissions.
    
    Note: This is temporary and will be replaced by more formal permissions
    when available. See the note under validate_auth() for further explanation.
    """

    mc_search = mediacloud.api.SearchApi(auth_key)

    try:
        mc_search.story_list(
            "mediacloud",
            start_date = date.today(),
            end_date = date.today() - timedelta(1),
            expanded = True)
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
        "state_type": run.state_type
    }


async def _store_credentials(auth_email:str, auth_key:str) -> Secret:
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


async def fetch_all_runs(tags:List[str]=[]) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Buffet runs from Prefect."""
    
    tags += DEFAULT_TAGS
    tags_filter = FlowRunFilter(tags=FlowRunFilterTags(all_=tags))

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=tags_filter)
        return [_run_to_dict(run) for run in runs]


async def fetch_current_runs(tags:List[str]=[]) -> List[Dict[str, Any]]:
    """Fetch any current or upcoming Sous Chef Buffet runs from Prefect."""

    tags += DEFAULT_TAGS
    states = [StateType.RUNNING, StateType.SCHEDULED, StateType.PENDING]
    
    states_filter = FlowRunFilter(
        state=FlowRunFilterState(type=FlowRunFilterStateType(any_=states)),
        tags=FlowRunFilterTags(all_=tags))

    async with prefect.get_client() as client:
        runs = await client.read_flow_runs(flow_run_filter=states_filter)
        return [_run_to_dict(run) for run in runs]


async def fetch_run_by_id(run_id: UUID | str) -> Dict[str, Any]:
    """Fetch a specific Sous Chef Buffet run from Prefect by its ID."""

    if type(run_id) is str:
        try:
            run_id = UUID(run_id)
        except:
            raise ValueError(
                f"Failed to parse the string as a UUID for {run_id}.")

    async with prefect.get_client() as client:
        run = await client.read_flow_run(run_id)
        return _run_to_dict(run)


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


@flow(name=PREFECT_DEPLOYMENT)
async def start_recipe(recipe_name: str, tags:List[str]=[],
    parameters:Dict[str, str]=None) -> FlowRun:
    """Handle orders for the requested recipe from the sous chef buffet."""

    # NOTE: Refactoring this after realizing it did not block extracting the
    # output from the QueryOnlineNews atom from the client side as well as
    # I thought it did. Purging the corresponding return values from RunPipeline
    # seems to work in most but not all cases.

    order = SousChefBaseOrder(**parameters)
    
    recipe_folder = recipe.get_recipe_folder(recipe_name)
    with open(f"{recipe_folder/"recipe.yaml"}", "r") as f:
        recipe = f.read()
    
    conf = recipe_loader.t_yaml_to_conf(recipe, **order.dict())
    conf["name"] = order.NAME
    run_data = RunPipeline(conf)

    # TODO: Re-add QueryOnlineNews return value cleanup here
    # TODO: Re-add task to create_table_artifact from run_data here after cleanup
     

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
    status.sous_chef_authorized = bool(await _store_credentials(auth_email, auth_key))

    return status
