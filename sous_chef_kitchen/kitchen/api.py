"""
Field requests to the Sous Chef Kitchen API.
"""

from typing import Annotated, Any, Dict, List
from uuid import UUID

from fastapi import Depends, FastAPI, Request, Response, status as http_status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import logging

from sous_chef_kitchen.kitchen import chef
from sous_chef_kitchen.shared.models import \
	SousChefKitchenAuthStatus, SousChefKitchenSystemStatus

app = FastAPI()
security = HTTPBearer()
bearer = Annotated[HTTPAuthorizationCredentials, Depends(security)]
logger = logging.getLogger(__name__)


async def _validate_auth(auth: bearer, request: Request, response: Response) \
	-> SousChefKitchenAuthStatus:
	"""Check whether the API key is authorized for Media Cloud and Sous Chef."""

	auth_email = request.headers.get("mediacloud-email")
	auth_key = auth.credentials

	auth_status = await chef.validate_auth(auth_email, auth_key)
	if not auth_status.authorized:
		response.status_code = http_status.HTTP_403_FORBIDDEN
	logger.info(f"Auth status {auth_status}")
	return auth_status


@app.get("/")
def get_root(response: Response) -> None:
	"""Be very demure and very mindful."""

	response.status_code = http_status.HTTP_204_NO_CONTENT
	return


@app.post("/recipe/start")
async def start_recipe(auth: bearer, request: Request, response: Response) \
	-> Dict[str, Any] | SousChefKitchenAuthStatus:
	"""Fetch all Sous Chef Kitchen runs from Prefect."""
	
	auth_status = await _validate_auth(auth, request, response)
	if not auth_status.authorized:
		return auth_status
	
	# TODO: Fix bearer token vs function signature issue
	recipe_name = request.query_params["recipe_name"]
	logger.info(f"Start recipe {recipe_name}")
	return await chef.start_recipe(recipe_name)


@app.post("/recipe/schema")
async def recipe_schema(auth:bearer, request: Request, response: Response) \
	-> Dict[str, Any]:

	auth_status = await _validate_auth(auth, request, response)
	if not auth_status.authorized:
		return auth_status
	
	# TODO: Fix bearer token vs function signature issue
	recipe_name = request.query_params["recipe_name"]
	logger.info(f"Get recipe schema for {recipe_name}")
	return await chef.recipe_schema(recipe_name)


@app.get("/runs/active")
async def fetch_active_runs(auth: bearer, request: Request, response: Response) \
	-> List[Dict[str, Any]] | SousChefKitchenAuthStatus:
	"""Fetch any active or upcoming Sous Chef Kitchen runs from Prefect."""
	
	auth_status = await _validate_auth(auth, request, response)
	if not auth_status.authorized:
		return auth_status
	
	return await chef.fetch_active_runs()


@app.post("/runs/cancel")
async def cancel_recipe_run(auth: bearer, request: Request, response: Response) \
	-> List[Dict[str, Any]] | SousChefKitchenAuthStatus:
	"""Cancel the specified Sous Chef Kitchen run."""

	auth_status = await _validate_auth(auth, request, response)
	if not auth_status.authorized:
		return auth_status

	# TODO: Fix bearer token vs function signature issue
	recipe_name = request.query_params["recipe_name"]
	run_id = request.query_params["run_id"]
	
	return await chef.cancel_recipe_run(recipe_name, run_id)


@app.post("/runs/pause")
async def pause_recipe_run(auth: bearer, request: Request, response: Response) \
	-> List[Dict[str, Any]] | SousChefKitchenAuthStatus:
	"""Pause the specified Sous Chef Kitchen run."""

	auth_status = await _validate_auth(auth, request, response)
	if not auth_status.authorized:
		return auth_status

	# TODO: Fix bearer token vs function signature issue
	recipe_name = request.query_params["recipe_name"]
	run_id = request.query_params["run_id"]
	
	return await chef.pause_recipe_run(recipe_name, run_id)


@app.post("/runs/resume")
async def resume_recipe_run(auth: bearer, request: Request, response: Response) \
	-> List[Dict[str, Any]] | SousChefKitchenAuthStatus:
	"""Resume the specified Sous Chef Kitchen run."""

	auth_status = await _validate_auth(auth, request, response)
	if not auth_status.authorized:
		return auth_status

	# TODO: Fix bearer token vs function signature issue
	recipe_name = request.query_params["recipe_name"]
	run_id = request.query_params["run_id"]
	
	return await chef.resume_recipe_run(recipe_name, run_id)



@app.get("/runs/all")
async def fetch_all_runs(auth: bearer, request: Request, response: Response) \
	-> List[Dict[str, Any]] | SousChefKitchenAuthStatus:
	"""Fetch all Sous Chef Kitchen runs from Prefect."""
	
	auth_status = await _validate_auth(auth, request, response)
	if not auth_status.authorized:
		return auth_status
	
	return await chef.fetch_all_runs()


@app.get("/run/{run_id}")
async def fetch_run_by_id(run_id: str, auth: bearer, request: Request,
	response: Response) -> Dict[str, Any] | SousChefKitchenAuthStatus:
	"""Fetch a specific Sous Chef Kitchen run from Prefect by its ID."""
	
	auth_status = await _validate_auth(auth, request, response)
	if not auth_status.authorized:
		return auth_status

	try:	
		return await chef.fetch_run_by_id(run_id)
	except ValueError as e:
		# TODO: Pass through the error message from the exception
		response.status_code = http_status.HTTP_400_BAD_REQUEST


@app.get("/auth/validate", response_model=SousChefKitchenAuthStatus)
async def validate_auth(auth: bearer, request: Request, response: Response) \
	-> SousChefKitchenAuthStatus:
	"""Check whether the API key is authorized for Media Cloud and Sous Chef."""

	return await _validate_auth(auth, request, response)


@app.get("/system/status", response_model=SousChefKitchenSystemStatus)
async def get_system_status(response: Response) -> SousChefKitchenSystemStatus:
	"""Check whether the Sous Chef backend systems are available and ready."""

	system_status = await chef.get_system_status()
	if not system_status.ready:
		response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
	return system_status
