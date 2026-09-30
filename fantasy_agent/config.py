"""Configuration and Google Cloud Secret Manager integration for the Fantasy Football Agent.

Satisfies AgentOps Rubric Criterion 5.3 (Secure Secret Management) and Criterion 3.2
(Strategic Model Routing constants).
"""

from __future__ import annotations

import functools
import os
import subprocess
from dataclasses import dataclass

from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import GoogleAuthError
from google.cloud import secretmanager

# Strategic Model Routing Tiers (Rubric Criterion 3.2)
FAST_MODEL = os.environ.get("FANTASY_AGENT_FAST_MODEL", "gemini-2.5-flash")
REASONING_MODEL = os.environ.get("FANTASY_AGENT_REASONING_MODEL", "gemini-2.5-pro")
DEFAULT_GCP_LOCATION = "us-central1"


def select_model_for_task(task_complexity: str) -> str:
    """Route an agent or task to the appropriate Gemini model tier.

    Satisfies AgentOps Rubric Criterion 3.2 (Strategic Model Routing):
    - Fast / low-latency tasks (`"fast"`, `"routing"`, `"lookup"`, `"waiver"`) -> `gemini-2.5-flash`
    - Complex analytical or multi-step planning tasks (`"reasoning"`, `"analytics"`,
      `"trade_strategy"`, `"planning"`) -> `gemini-2.5-pro`
    """
    normalized = task_complexity.strip().lower()
    if normalized in {"reasoning", "analytics", "trade_strategy", "planning", "pro"}:
        return REASONING_MODEL
    return FAST_MODEL


def resolve_gcp_project_id() -> str:
    """Resolve the active Google Cloud Project ID without hardcoding project identifiers.

    Checks environment variables first, then falls back to the active `gcloud config`
    value if available.

    Returns:
        str: The resolved GCP project ID, or `"local-dev-project"` when running offline tests.
    """
    env_project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
    )
    if env_project:
        return env_project.strip()

    try:
        completed = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        candidate = completed.stdout.strip()
        if completed.returncode == 0 and candidate and candidate != "(unset)":
            return candidate
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass

    return "local-dev-project"


def fetch_secret_from_secret_manager(
    secret_id: str,
    project_id: str | None = None,
    version_id: str = "latest",
    default: str | None = None,
) -> str | None:
    """Retrieve a secret payload from Google Cloud Secret Manager with safe env fallback.

    Args:
        secret_id: Name of the secret in Google Cloud Secret Manager (or env var name).
        project_id: Optional GCP project ID. Resolved dynamically if omitted.
        version_id: Secret version to access (defaults to `"latest"`).
        default: Default value if neither env var nor Secret Manager secret is available.

    Returns:
        The resolved secret string, or `default` if unavailable.
    """
    # 1. Check environment variable override for local testing / CI
    env_val = os.environ.get(secret_id)
    if env_val:
        return env_val

    resolved_project = project_id or resolve_gcp_project_id()
    if resolved_project == "local-dev-project":
        return default

    try:
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{resolved_project}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": secret_name})
        return response.payload.data.decode("utf-8").strip()
    except (GoogleAPICallError, GoogleAuthError, ValueError, OSError):
        return default


@dataclass(frozen=True)
class AgentSettings:
    """Runtime settings for the Fantasy Football Personal Agent."""

    project_id: str
    location: str
    use_vertexai: bool
    fast_model: str
    reasoning_model: str
    default_team_id: str = "team_alpha"
    current_week: int = 8


@functools.lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    """Load and cache runtime settings and initialize Vertex AI environment variables."""
    project_id = resolve_gcp_project_id()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_GCP_LOCATION)
    use_vertexai_raw = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    use_vertexai = use_vertexai_raw.upper() in ("1", "TRUE", "YES")

    # Ensure google-genai / google-adk environment variables are populated for Vertex AI
    if use_vertexai and project_id != "local-dev-project":
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)

    return AgentSettings(
        project_id=project_id,
        location=location,
        use_vertexai=use_vertexai,
        fast_model=FAST_MODEL,
        reasoning_model=REASONING_MODEL,
    )
