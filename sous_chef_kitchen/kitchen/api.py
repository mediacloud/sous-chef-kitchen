"""
Field requests to the Sous Chef Kitchen API.
"""

import json
import logging
import re
from typing import Annotated, Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi import status as http_status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
    allow_headers=["*"],
)


def _parse_validation_error(error_msg: str) -> Dict[str, List[str]]:
    """
    Parse validation error messages to extract field-specific errors.

    Attempts to extract field names and error messages from error strings.
    Returns a dictionary mapping field names to lists of error messages.
    """
    errors = {}

    # Try to match patterns like "field_name: error message" or "field_name -> error"
    # Common patterns from Pydantic errors
    patterns = [
        r"(\w+):\s*([^\n]+)",  # "field: error message"
        r"'(\w+)':\s*([^\n]+)",  # "'field': error message"
        r"(\w+)\s*->\s*([^\n]+)",  # "field -> error"
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, error_msg)
        for match in matches:
            field_name = match.group(1)
            error_message = match.group(2).strip()
            if field_name not in errors:
                errors[field_name] = []
            errors[field_name].append(error_message)

    # If no structured errors found, return general error
    if not errors:
        errors["_general"] = [error_msg]

    return errors


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
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params.get("recipe_name")
    if not recipe_name:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: recipe_name",
        )

    # Parse and validate request body
    try:
        recipe_parameters = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in request body: {str(e)}",
        )

    if not isinstance(recipe_parameters, dict):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Request body must be a JSON object",
        )

    if "recipe_parameters" not in recipe_parameters:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required field: recipe_parameters",
        )

    recipe_parameters = recipe_parameters["recipe_parameters"]
    logger.info(f"Start recipe {recipe_name}")

    # Extract authenticated user's email from request headers
    auth_email = request.headers.get("mediacloud-email")

    try:
        return await chef.start_recipe(
            recipe_name=recipe_name,
            parameters=recipe_parameters,
            tags=[auth_status.tag_slug],
            user_full_text_authorized=auth_status.media_cloud_full_text_authorized,
            auth_email=auth_email,
        )
    except ValueError as e:
        logger.error(f"Validation error starting recipe {recipe_name}: {e}")
        error_msg = str(e)

        # Try to parse validation errors for structured response
        if (
            "Error validating parameters" in error_msg
            or "Parameter validation failed" in error_msg
        ):
            parsed_errors = _parse_validation_error(error_msg)
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Parameter validation failed",
                    "errors": parsed_errors,
                },
            )
        else:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST, detail=error_msg
            )
    except RuntimeError as e:
        logger.error(f"Runtime error starting recipe {recipe_name}: {e}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Unexpected error starting recipe {recipe_name}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while starting the recipe",
        )


@app.get("/recipe/schema")
async def recipe_schema(
    auth: bearer, request: Request, response: Response
) -> Dict[str, Any]:

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(
            f"Unauthorized access attempt to get recipe schema: {auth_status}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params.get("recipe_name")
    if not recipe_name:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: recipe_name",
        )
    logger.info(f"Get recipe schema for {recipe_name}")
    try:
        return await chef.recipe_schema(recipe_name)
    except ValueError as e:
        logger.warning(f"Recipe schema not found for {recipe_name}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Recipe '{recipe_name}' not found",
        )


@app.get("/recipe/list")
async def recipe_list(
    auth: bearer, request: Request, response: Response
) -> Dict[str, Any]:
    logger.info("Recipe list endpoint called")
    auth_status = await _validate_auth(auth, request, response)

    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to recipe list: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )
    logger.info("Fetching recipe list")
    try:
        recipe_list_result = await chef.recipe_list()
        logger.info(
            f"Recipe list fetched successfully: {len(recipe_list_result)} recipes found"
        )
        return recipe_list_result
    except Exception as e:
        logger.error(f"Error fetching recipe list: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching the recipe list",
        )


@app.get("/runs/active")
async def fetch_active_runs(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Fetch any active or upcoming Sous Chef Kitchen runs from Prefect."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(
            f"Unauthorized access attempt to fetch active runs: {auth_status}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    try:
        return await chef.fetch_active_runs(tags=[])
    except Exception as e:
        logger.error(f"Error fetching active runs: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching active runs",
        )


@app.post("/runs/cancel")
async def cancel_recipe_run(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Cancel the specified Sous Chef Kitchen run."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(
            f"Unauthorized access attempt to cancel recipe run: {auth_status}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params.get("recipe_name")
    run_id = request.query_params.get("run_id")
    if not recipe_name:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: recipe_name",
        )
    if not run_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: run_id",
        )

    try:
        # For regular users, pass their tag for authorization check
        # For admins, pass empty tags (will only check BASE_TAGS)
        user_tags = [] if auth_status.media_cloud_staff else [auth_status.tag_slug]
        return await chef.cancel_recipe_run(recipe_name, run_id, tags=user_tags)
    except ValueError as e:
        logger.warning(f"Error canceling recipe run {run_id}: {e}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Runtime error canceling recipe run {run_id}: {e}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Unexpected error canceling recipe run {run_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while canceling the recipe run",
        )


@app.post("/runs/pause")
async def pause_recipe_run(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Pause the specified Sous Chef Kitchen run."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(
            f"Unauthorized access attempt to pause recipe run: {auth_status}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params.get("recipe_name")
    run_id = request.query_params.get("run_id")
    if not recipe_name:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: recipe_name",
        )
    if not run_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: run_id",
        )

    try:
        return await chef.pause_recipe_run(recipe_name, run_id)
    except ValueError as e:
        logger.warning(f"Error pausing recipe run {run_id}: {e}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Unexpected error pausing recipe run {run_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while pausing the recipe run",
        )


@app.post("/runs/resume")
async def resume_recipe_run(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Resume the specified Sous Chef Kitchen run."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(
            f"Unauthorized access attempt to resume recipe run: {auth_status}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    # TODO: Fix bearer token vs function signature issue
    recipe_name = request.query_params.get("recipe_name")
    run_id = request.query_params.get("run_id")
    if not recipe_name:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: recipe_name",
        )
    if not run_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing required query parameter: run_id",
        )

    try:
        return await chef.resume_recipe_run(recipe_name, run_id)
    except ValueError as e:
        logger.warning(f"Error resuming recipe run {run_id}: {e}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Unexpected error resuming recipe run {run_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resuming the recipe run",
        )


@app.get("/runs/all")
async def fetch_all_runs(
    auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Kitchen runs from Prefect."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to fetch all runs: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    try:
        return await chef.fetch_all_runs(tags=[])
    except Exception as e:
        logger.error(f"Error fetching all runs: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching runs",
        )


@app.get("/runs/list")
async def fetch_user_runs(
    auth: bearer,
    request: Request,
    response: Response,
    parent_only: bool = True,
    all_users: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch all Sous Chef Kitchen runs from Prefect, filtering based on generated auth slug.

    By default, only returns parent runs (excludes child/subflow runs).
    Set parent_only=false to include all runs including child runs.
    For admin users (media_cloud_staff=True), set all_users=true to see all runs in the system.
    """

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to fetch user runs: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    # Check if user is requesting all runs and is authorized to do so
    if all_users:
        if not auth_status.media_cloud_staff:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Only admin users can view all runs. Set all_users=false or omit the parameter.",
            )
        # Admin viewing all runs - only filter by BASE_TAGS (no user tag)
        tags_to_use = []
    else:
        # Regular user or admin viewing their own runs - filter by user tag
        tags_to_use = [auth_status.tag_slug]

    try:
        return await chef.fetch_all_runs(tags=tags_to_use, parent_only=parent_only)
    except Exception as e:
        logger.error(f"Error fetching user runs: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching user runs",
        )


@app.get("/run/{run_id}")
async def fetch_run_by_id(
    run_id: str, auth: bearer, request: Request, response: Response
) -> Dict[str, Any]:
    """Fetch a specific Sous Chef Kitchen run from Prefect by its ID."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(f"Unauthorized access attempt to fetch run by ID: {auth_status}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    try:
        return await chef.fetch_run_by_id(run_id)
    except ValueError as e:
        logger.warning(f"Invalid run ID {run_id}: {e}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/run/{run_id}/artifacts")
async def fetch_run_artifacts(
    run_id: str, auth: bearer, request: Request, response: Response
) -> List[Dict[str, Any]]:
    """Fetch artifacts for a specific run."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(
            f"Unauthorized access attempt to fetch run artifacts: {auth_status}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    try:
        return await chef.fetch_run_artifacts(run_id)
    except ValueError as e:
        logger.warning(f"Invalid run ID for artifacts {run_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid run ID: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Failed to fetch run artifacts for {run_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching run artifacts",
        )


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


@app.get("/user/flow-status")
async def get_user_flow_status(
    auth: bearer, request: Request, response: Response
) -> Dict[str, Any]:
    """Get the current user's active flow count and max limit."""

    auth_status = await _validate_auth(auth, request, response)
    if not auth_status.authorized:
        logger.warning(
            f"Unauthorized access attempt to get user flow status: {auth_status}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Authentication failed"
        )

    from sous_chef_kitchen.kitchen.chef import MAX_USER_FLOWS, fetch_active_runs

    active_runs = await fetch_active_runs(tags=[auth_status.tag_slug])
    active_count = len(active_runs)

    return {
        "active_flows": active_count,
        "max_flows": MAX_USER_FLOWS,
        "at_capacity": active_count >= MAX_USER_FLOWS,
    }
