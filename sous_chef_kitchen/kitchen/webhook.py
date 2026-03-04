"""
Webhook notification functionality for Sous Chef Kitchen.

This module handles sending webhook notifications when flow runs complete,
providing run status, artifact metadata, and error information to external systems.
"""

import logging
import time
from datetime import datetime
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
    # Build artifact summary (metadata only, not full data)
    artifact_summary = []
    if artifacts:
        for task_name, output in artifacts.items():
            data = output.get("data")
            # Determine artifact type and row count
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
                # BaseArtifact instance
                artifact_type = getattr(data, "artifact_type", "artifact")
                if hasattr(data, "to_table"):
                    try:
                        table = data.to_table()
                        row_count = len(table) if isinstance(table, list) else None
                    except Exception:
                        pass
            elif isinstance(data, tuple) and len(data) == 2:
                # Handle tuple returns: (result, artifact)
                result, artifact = data
                if BaseArtifact is not None and isinstance(artifact, BaseArtifact):
                    artifact_type = getattr(artifact, "artifact_type", "artifact")
                    if hasattr(artifact, "to_table"):
                        try:
                            table = artifact.to_table()
                            row_count = len(table) if isinstance(table, list) else None
                        except Exception:
                            pass

            artifact_summary.append(
                {
                    "key": task_name,
                    "type": artifact_type,
                    "row_count": row_count,
                    "restricted": output.get("restricted", False),
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
        "artifacts": artifact_summary,
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
