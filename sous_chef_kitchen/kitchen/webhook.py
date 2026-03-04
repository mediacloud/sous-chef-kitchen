"""
Webhook notification functionality for Sous Chef Kitchen.

This module handles sending webhook notifications when flow runs complete,
providing run status, artifact metadata, and error information to external systems.
"""

import logging
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

# Import BaseArtifact for artifact detection
try:
    from sous_chef.artifacts import BaseArtifact
except ImportError:
    # Fallback if artifacts module not available
    BaseArtifact = None

logger = logging.getLogger("sous_chef_kitchen.webhook")


def _serialize_artifact_data(data: Any) -> Any:
    """
    Serialize artifact data to JSON-compatible format.

    Handles various data types:
    - DataFrames: Convert to list of dicts with date serialization
    - BaseArtifact: Convert via to_table() method
    - Tuples: Handle (result, artifact) pattern
    - Lists/Dicts: Return as-is (assumed JSON-serializable)
    - Other: Wrap in dict

    Args:
        data: Artifact data to serialize

    Returns:
        JSON-serializable data structure
    """
    # Handle tuple returns: (result, artifact)
    if isinstance(data, tuple) and len(data) == 2:
        result, artifact = data
        # For webhooks, we'll include both result and artifact data
        serialized = {}

        # Serialize result
        if result is not None:
            if isinstance(result, pd.DataFrame):
                serialized["result"] = _df_to_records(result)
            elif isinstance(result, (list, dict)):
                serialized["result"] = result
            else:
                serialized["result"] = {"value": result}

        # Serialize artifact if present
        if (
            artifact is not None
            and BaseArtifact is not None
            and isinstance(artifact, BaseArtifact)
        ):
            try:
                serialized["artifact"] = artifact.to_table()
                serialized["artifact_type"] = getattr(
                    artifact, "artifact_type", "artifact"
                )
            except Exception as e:
                logger.warning(f"Failed to serialize artifact: {e}")
                serialized["artifact"] = None

        return serialized

    # Handle BaseArtifact instance
    if BaseArtifact is not None and isinstance(data, BaseArtifact):
        try:
            table = data.to_table()
            artifact_type = getattr(data, "artifact_type", "artifact")
            return {"data": table, "artifact_type": artifact_type}
        except Exception as e:
            logger.warning(f"Failed to serialize BaseArtifact: {e}")
            return {"data": None, "artifact_type": "unknown"}

    # Handle DataFrame
    if isinstance(data, pd.DataFrame):
        return _df_to_records(data)

    # Handle list or dict (assume already JSON-serializable)
    if isinstance(data, (list, dict)):
        return data

    # Fallback: wrap in dict
    return {"value": data}


def _df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Convert DataFrame to records with proper date serialization.

    This ensures that date and datetime columns are converted to ISO format strings
    for JSON serialization compatibility.

    Args:
        df: DataFrame to convert

    Returns:
        List of dict records with dates serialized to strings
    """
    if df.empty:
        return []

    # Make a copy to avoid modifying the original
    df_copy = df.copy()

    # Convert datetime64 columns to strings
    for col in df_copy.columns:
        if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
            # Convert datetime columns to ISO format strings
            df_copy[col] = (
                df_copy[col].dt.strftime("%Y-%m-%dT%H:%M:%S").replace("NaT", None)
            )
        elif df_copy[col].dtype == "object":
            # Check if column contains date/datetime objects (not datetime64)
            sample = df_copy[col].dropna()
            if len(sample) > 0 and isinstance(sample.iloc[0], (date, datetime)):
                df_copy[col] = df_copy[col].apply(
                    lambda x: x.isoformat() if isinstance(x, (date, datetime)) else x
                )

    return df_copy.to_dict("records")


def fire_webhook(
    webhook_url: str,
    webhook_secret: Optional[str],
    flow_run_id: str,
    recipe_name: str,
    tags: List[str],
    parameters: Dict,
    success: bool,
    error: Optional[str],
    artifacts: Optional[Dict[str, Dict[str, Any]]],
) -> None:
    """
    Fire webhook notification to provided URL.

    This is a best-effort operation - failures are logged but don't affect flow execution.

    Args:
        webhook_url: URL to send POST request to
        webhook_secret: Optional secret token for authentication
        flow_run_id: Prefect flow run ID
        recipe_name: Name of the recipe/flow that was executed
        tags: Tags associated with the run
        parameters: Flow parameters (will be sanitized)
        success: Whether execution succeeded
        error: Error message if execution failed
        artifacts: Artifact data if execution succeeded
    """
    # Build artifact list with full data
    artifact_list = []
    if artifacts:
        for task_name, output in artifacts.items():
            data = output.get("data")
            restricted = output.get("restricted", False)

            # Determine artifact type and row count for metadata
            artifact_type = "unknown"
            row_count = None

            if isinstance(data, pd.DataFrame):
                artifact_type = "table"
                row_count = len(data)
            elif isinstance(data, list):
                artifact_type = "table"
                row_count = len(data)
            elif isinstance(data, dict):
                artifact_type = "object"
                row_count = 1
            elif BaseArtifact is not None and isinstance(data, BaseArtifact):
                artifact_type = getattr(data, "artifact_type", "artifact")
                if hasattr(data, "to_table"):
                    try:
                        table = data.to_table()
                        row_count = len(table) if isinstance(table, list) else None
                    except Exception:
                        pass
            elif isinstance(data, tuple) and len(data) == 2:
                result, artifact = data
                if BaseArtifact is not None and isinstance(artifact, BaseArtifact):
                    artifact_type = getattr(artifact, "artifact_type", "artifact")
                    if hasattr(artifact, "to_table"):
                        try:
                            table = artifact.to_table()
                            row_count = len(table) if isinstance(table, list) else None
                        except Exception:
                            pass
                # For tuple, also check result
                if isinstance(result, pd.DataFrame):
                    row_count = len(result) if row_count is None else row_count
                elif isinstance(result, list):
                    row_count = len(result) if row_count is None else row_count

            # Serialize the full artifact data
            try:
                serialized_data = _serialize_artifact_data(data)
            except Exception as e:
                logger.warning(f"Failed to serialize artifact '{task_name}': {e}")
                serialized_data = {"error": f"Serialization failed: {str(e)}"}

            artifact_list.append(
                {
                    "key": task_name,
                    "type": artifact_type,
                    "row_count": row_count,
                    "restricted": restricted,
                    "data": serialized_data,  # Full artifact data
                }
            )

    # Build webhook payload
    payload = {
        "run": {
            "id": str(flow_run_id),
            "recipe_name": recipe_name,
            "status": "completed" if success else "failed",
            "state_type": "COMPLETED" if success else "FAILED",
            "state_name": "Completed" if success else "Failed",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "tags": tags,
            # Sanitize parameters - remove webhook params and any secrets
            "parameters": sanitize_parameters(parameters),
        },
        "artifacts": artifact_list,
    }

    # Add error info if failed
    if not success and error:
        payload["error"] = {"message": error}

    # Add metadata
    payload["metadata"] = {
        "webhook_version": "1.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Sous-Chef-Kitchen/1.0",
    }
    if webhook_secret:
        headers["X-Webhook-Secret"] = webhook_secret

    # Fire webhook with retry logic
    max_retries = 3
    timeout = 10.0  # seconds

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    str(webhook_url),
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                logger.info(
                    f"Webhook delivered successfully to {webhook_url} (attempt {attempt + 1})"
                )
                return

        except httpx.HTTPError as e:
            if attempt == max_retries - 1:
                status_code = (
                    e.response.status_code
                    if hasattr(e, "response") and e.response
                    else "N/A"
                )
                logger.warning(
                    f"Webhook delivery failed after {max_retries} attempts: {e}. "
                    f"URL: {webhook_url}, Status: {status_code}"
                )
                raise
            # Exponential backoff
            time.sleep(2**attempt)
            logger.debug(f"Webhook attempt {attempt + 1} failed, retrying: {e}")


def sanitize_parameters(parameters: Dict) -> Dict:
    """
    Remove sensitive parameters from webhook payload.

    Excludes webhook_url, webhook_secret, and any other sensitive fields.

    Args:
        parameters: Original parameters dict

    Returns:
        Sanitized parameters dict with sensitive fields removed
    """
    sensitive_keys = {
        "webhook_url",
        "webhook_secret",
        "api_key",
        "password",
        "secret",
        "token",
    }
    sanitized = {}
    for key, value in parameters.items():
        if key.lower() not in sensitive_keys:
            sanitized[key] = value
    return sanitized
