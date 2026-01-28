"""
Provide a menu of client-side handlers for orders to the Sous Chef Kitchen API
used by both the CLI and web clients.
"""

import json
import os
import urllib.parse
from http import HTTPStatus
from typing import Any, Dict
from uuid import UUID

import requests
from requests import ConnectionError

from sous_chef_kitchen.shared.models import (
    SousChefKitchenAuthStatus,
    SousChefKitchenSystemStatus,
)

DEFAULT_API_BASE_URL = "https://kitchen-staging.tarbell.mediacloud.org"
DEFAULT_API_USER_AGENT = "Sous Chef Kitchen"

API_AUTH_EMAIL = os.getenv("SC_API_AUTH_EMAIL")
API_AUTH_KEY = os.getenv("SC_API_AUTH_KEY")
API_BASE_URL = os.getenv("SC_API_BASE_URL", DEFAULT_API_BASE_URL)
API_USER_AGENT = os.getenv("SC_API_USER_AGENT", DEFAULT_API_USER_AGENT)


class SousChefKitchenAPIClient:
    """A client for handling interactions with the Sous Chef Kitchen API."""

    def __init__(
        self,
        auth_email=API_AUTH_EMAIL,
        auth_key=API_AUTH_KEY,
        base_url=API_BASE_URL,
        user_agent=API_USER_AGENT,
    ) -> None:
        """Initialize the Sous Chef Kitchen API client."""

        self.auth_email = auth_email
        self.auth_key = auth_key
        self.base_url = base_url
        self.user_agent = user_agent

        self._session = self._init_session()

    def _raise_for_status_with_detail(self, response):
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            print("Status code:", e.response.status_code)
            try:
                print("Detail message:", e.response.json()["detail"])
            except Exception:
                print("Raw response:", e.response.text)
            raise

    def _init_session(self) -> requests.Session:
        """Initialize a session with the API."""

        session = requests.Session()
        session.headers.update({"Accept": "application/json"})
        session.headers.update({"User-Agent": self.user_agent})
        if self.auth_email:
            session.headers.update({"mediacloud-email": self.auth_email})
        if self.auth_key:
            session.headers.update({"Authorization": f"Bearer {self.auth_key}"})

        return session

    def fetch_all_runs(self) -> Dict[str, Any] | SousChefKitchenAuthStatus:
        """Fetch all Sous Chef Kitchen runs from Prefect."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "runs/all")

        response = self._session.get(url)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def fetch_user_runs(self) -> Dict[str, Any] | SousChefKitchenAuthStatus:
        """Fetch all Sous Chef Kitchen runs from Prefect."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "runs/list")

        response = self._session.get(url)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def fetch_active_runs(self) -> Dict[str, Any] | SousChefKitchenAuthStatus:
        """Fetch any active or upcoming Sous Chef Kitchen runs from Prefect."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "runs/active")

        response = self._session.get(url)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def fetch_run_by_id(
        self, run_id: UUID | str
    ) -> Dict[str, Any] | SousChefKitchenAuthStatus:
        """Fetch a specific Sous Chef Kitchen run from Prefect by its ID."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, f"run/{run_id}")

        response = self._session.get(url)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def fetch_run_artifacts(self, run_id: UUID | str) -> Dict[str, Any]:
        """fetch artifacts associated with a completed sous-chef run"""
        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, f"run/{run_id}/artifacts")

        response = self._session.get(url)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def fetch_system_status(self) -> SousChefKitchenSystemStatus:
        """Check whether the Sous Che backend systems are available and ready."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.SERVICE_UNAVAILABLE}
        url = urllib.parse.urljoin(self.base_url, "system/status")

        try:
            response = self._session.get(url)
            if response.status_code in expected_responses:
                return SousChefKitchenSystemStatus.model_validate(response.json())
            response.raise_for_status()
        except ConnectionError:
            return SousChefKitchenSystemStatus()

    def recipe_list(self) -> Dict[str, Any]:
        expected_responses = {HTTPStatus.OK}
        url = urllib.parse.urljoin(self.base_url, "recipe/list")
        print(url)
        response = self._session.get(url)
        print(response.status_code)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def recipe_schema(self, recipe_name: str) -> Dict[str, Any]:
        """Return the expected parameter values for a given recipe"""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "recipe/schema")
        params = {"recipe_name": recipe_name}

        response = self._session.get(url, params=params)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def start_recipe(self, recipe_name: str, recipe_parameters: Dict) -> Dict[str, Any]:
        """Start a Sous Chef recipe."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "recipe/start")
        params = {"recipe_name": recipe_name}

        # Attempt to generically handle any array-type parameters based on the recipe schema
        try:
            schema = self.recipe_schema(recipe_name)
            # Schema may either be a flat dict of field definitions or a JSON Schema with "properties"
            if isinstance(schema, dict):
                properties = schema.get("properties", schema)
            else:
                properties = {}

            # Collect all parameters declared as arrays
            array_params = [
                param_name
                for param_name, param_def in properties.items()
                if isinstance(param_def, dict) and param_def.get("type") == "array"
            ]
        except Exception:
            # If we can't fetch/parse the schema, fall back to known array params
            array_params = ["COLLECTIONS", "SOURCES"]

        # Normalize all array-type parameters:
        # - If value is a JSON string, parse it
        # - If not a list, wrap in a list
        # - Convert all items to strings for transport
        for param_name in array_params:
            if param_name in recipe_parameters:
                try:
                    value = recipe_parameters[param_name]
                    if isinstance(value, str):
                        # Try JSON-parsing string values like "[1, 2, 3]"
                        value = json.loads(value)

                    if not isinstance(value, list):
                        value = [value]

                    recipe_parameters[param_name] = [str(item) for item in value]
                except json.JSONDecodeError:
                    # If it's not valid JSON, assume it's a single value and coerce to a single-item list
                    recipe_parameters[param_name] = [str(recipe_parameters[param_name])]

        response = self._session.post(
            url, params=params, json={"recipe_parameters": recipe_parameters}
        )
        if response.status_code in expected_responses:
            return response.json()
        self._raise_for_status_with_detail(response)

    def cancel_recipe(self, recipe_name: str, run_id: UUID | str) -> Dict[str, Any]:
        """Cancel a Sous Chef recipe run."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "runs/cancel")
        params = {"recipe_name": recipe_name, "run_id": run_id}

        response = self._session.post(url, params=params)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def pause_recipe(self, recipe_name: str, run_id: UUID | str) -> Dict[str, Any]:
        """Pause a Sous Chef recipe run."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "runs/pause")
        params = {"recipe_name": recipe_name, "run_id": run_id}

        response = self._session.post(url, params=params)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def resume_recipe(self, recipe_name: str, run_id: UUID | str) -> Dict[str, Any]:
        """Resume a Sous Chef recipe run."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "runs/resume")
        params = {"recipe_name": recipe_name, "run_id": run_id}

        response = self._session.post(url, params=params)
        if response.status_code in expected_responses:
            return response.json()
        response.raise_for_status()

    def validate_auth(self) -> SousChefKitchenAuthStatus:
        """Check whether the API key is authorized for Media Cloud and Sous Chef."""

        expected_responses = {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
        url = urllib.parse.urljoin(self.base_url, "auth/validate")

        response = self._session.get(url)
        if response.status_code in expected_responses:
            return SousChefKitchenAuthStatus.model_validate(response.json())
        response.raise_for_status()
