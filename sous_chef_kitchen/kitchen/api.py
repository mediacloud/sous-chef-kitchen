"""
Field requests to the Sous Chef Kitchen API.
"""

import logging
from typing import Annotated, Any, Dict, List
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi import status as http_status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware

from sous_chef_kitchen.kitchen import chef
from sous_chef_kitchen.kitchen.logging_config import setup_logging
from sous_chef_kitchen.shared.models import (
    SousChefKitchenAuthStatus,
    SousChefKitchenSystemStatus,
)

# Setup logging
setup_logging()

app = FastAPI()
security = HTTPBearer()
bearer = Annotated[HTTPAuthorizationCredentials, Depends(security)]
logger = logging.getLogger("sous_chef_kitchen.api")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"]
    )

async def _validate_auth(
    auth: bearer, request: Request, response: Response
) -> SousChefKitchenAuthStatus:
    """Check whether the API key is authorized for Media Cloud and Sous Chef."""

    auth_email = request.headers.get("mediacloud-email")
    auth_key = auth.credentials

    logger.info(f"Validating auth for email: {auth_email}")
    
    # This also needs some work to return a more fine-grained auth status.
    auth_status = await chef.validate_auth(auth_email, auth_key)
    if not auth_status.authorized:
        logger.warning(f"Authentication failed for {auth_email}: {auth_status}")
        response.status_code = http_status.HTTP_403_FORBIDDEN
    else:
        logger.info(f"Authentication successful for {auth_email}: {auth_status}")
    return auth_status



@app.get("/")
def get_root(response: Response) -> None:
    """Be very demure and very mindful."""

    response.status_code = http_status.HTTP_204_NO_CONTENT
    return


@app.post("/recipe/start")
async def start_recipe(
    auth: bearer, request: Request, response: Response
) -> Dict[str, Any]:
    """Fetch all Sous Chef Kitchen runs from Prefect."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to start recipe: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params["recipe_name"]
    recipe_parameters = await request.json()
    recipe_parameters = recipe_parameters[
        "recipe_parameters"
    ]  # all hail King King the Kingth
    logger.info(f"Start recipe {recipe_name}")

    try:
        return await chef.start_recipe(
            recipe_name=recipe_name,
            parameters=recipe_parameters,
            tags=[auth_status.tag_slug],
            user_full_text_authorized=auth_status.media_cloud_full_text_authorized,
        )
    except Exception as e:
        logger.error(f"Error starting recipe: {e}")
        if hasattr(e, "message"):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST, detail=e.message
            )
        else:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e)
            )


@app.get("/recipe/schema")
async def recipe_schema(
    auth: bearer, request: Request, response: Response
) -> Dict[str, Any]:

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to get recipe schema: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params["recipe_name"]
    logger.info(f"Get recipe schema for {recipe_name}")
    try:
        return await chef.recipe_schema(recipe_name)
    except ValueError:
        response.status_code = http_status.HTTP_404_NOT_FOUND
        return


@app.get("/recipe/list")
async def recipe_list(
    auth: bearer, request: Request, response: Response
) -> Dict[str, Any]:
    logger.info("Recipe list endpoint called")
    auth_status = await _validate_auth(auth, request, response)

    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to recipe list: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )
    logger.info("Fetching recipe list")
    recipe_list_result = await chef.recipe_list()
    logger.info(f"Recipe list fetched successfully: {len(recipe_list_result)} recipes found")
    return recipe_list_result


@app.get("/runs/active")
async def fetch_active_runs(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Fetch any active or upcoming Sous Chef Kitchen runs from Prefect."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to fetch active runs: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    return await chef.fetch_active_runs(tags=[])


@app.post("/runs/cancel")
async def cancel_recipe_run(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Cancel the specified Sous Chef Kitchen run."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to cancel recipe run: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params["recipe_name"]
    run_id = request.query_params["run_id"]

    return await chef.cancel_recipe_run(recipe_name, run_id)


@app.post("/runs/pause")
async def pause_recipe_run(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Pause the specified Sous Chef Kitchen run."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to pause recipe run: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params["recipe_name"]
    run_id = request.query_params["run_id"]

    return await chef.pause_recipe_run(recipe_name, run_id)


@app.post("/runs/resume")
async def resume_recipe_run(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Resume the specified Sous Chef Kitchen run."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to resume recipe run: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params["recipe_name"]
    run_id = request.query_params["run_id"]

    return await chef.resume_recipe_run(recipe_name, run_id)


@app.get("/runs/all")
async def fetch_all_runs(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Kitchen runs from Prefect."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to fetch all runs: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )
        
    return await chef.fetch_all_runs(tags=[])

@app.get("/runs/list")
async def fetch_user_runs(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """ Fetch all Sous Chef Kitchen runs from Prefect, filtering based on generated auth slug. """

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to fetch user runs: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    return await chef.fetch_all_runs(tags=[auth_status.tag_slug])



@app.get("/run/{run_id}")
async def fetch_run_by_id(
    run_id: str, auth: bearer, request: Request, response: Response
) -> Dict[str, Any]:
    """Fetch a specific Sous Chef Kitchen run from Prefect by its ID."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to fetch run by ID: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    try:
        return await chef.fetch_run_by_id(run_id)
    except ValueError:
        response.status_code = http_status.HTTP_400_BAD_REQUEST
        return None


@app.get("/run/{run_id}/artifacts")
async def fetch_run_artifacts(
    run_id: str, auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Fetch artifacts for a specific run."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to fetch run artifacts: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Authentication failed"
        )

    try:
        return await chef.fetch_run_artifacts(run_id)
    except Exception:
        logger.error("Failed to fetch run artifacts")
        raise


@app.get("/auth/validate", response_model=SousChefKitchenAuthStatus)
async def validate_auth(
    auth: bearer, request: Request, response: Response
) -> SousChefKitchenAuthStatus:
    """Check whether the API key is authorized for Media Cloud and Sous Chef."""

    return await _validate_auth(auth, request, response)


@app.get("/system/status", response_model=SousChefKitchenSystemStatus)
async def get_system_status(response: Response) -> SousChefKitchenSystemStatus:
    """Check whether the Sous Chef backend systems are available and ready."""

    system_status = await chef.get_system_status()
    if not system_status.ready:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
    return system_status
