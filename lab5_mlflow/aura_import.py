"""Tiny client helpers for Neo4j Aura Import API (v2beta1).

This module provides small, testable wrappers around the Aura Import API
endpoints used by the project: token retrieval, create import job, get job
status, and cancel job. All functions are synchronous and use `requests`.

These helpers intentionally keep behavior minimal and raise for HTTP
errors; callers should implement retries, backoff, and secrets management.
"""
from typing import Any, Dict, Optional
import os
import requests

DEFAULT_OAUTH_URL = os.environ.get('AURA_OAUTH_URL', 'https://api.neo4j.io/oauth/token')
DEFAULT_API_BASE = os.environ.get('AURA_API_BASE', 'https://api.neo4j.io/v2beta1')


def get_token(client_id: str, client_secret: str, oauth_url: str = DEFAULT_OAUTH_URL, timeout: int = 10) -> str:
    """Get an OAuth2 token via client_credentials. Returns the access token string.

    Raises requests.HTTPError on failure.
    """
    basic = requests.utils.to_native_string(requests.auth._basic_auth_str(client_id, client_secret))
    headers = {"Authorization": basic, "Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(oauth_url, headers=headers, data="grant_type=client_credentials", timeout=timeout)
    resp.raise_for_status()
    j = resp.json()
    return j.get('access_token')


def create_import_job(token: str, organization_id: str, project_id: str, import_model_id: str, db_id: str, api_base: str = DEFAULT_API_BASE, extra_body: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    """Create (run) an import job. Returns parsed JSON response.

    The body uses the minimal required fields; `extra_body` can add optional
    keys supported by your model configuration.
    """
    url = f"{api_base}/organizations/{organization_id}/projects/{project_id}/import/jobs"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body: Dict[str, Any] = {"importModelId": import_model_id, "auraCredentials": {"dbId": db_id}}
    if extra_body:
        body.update(extra_body)
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_job_status(token: str, organization_id: str, project_id: str, job_id: str, api_base: str = DEFAULT_API_BASE, timeout: int = 10) -> Dict[str, Any]:
    url = f"{api_base}/organizations/{organization_id}/projects/{project_id}/import/jobs/{job_id}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def cancel_job(token: str, organization_id: str, project_id: str, job_id: str, api_base: str = DEFAULT_API_BASE, timeout: int = 10) -> Dict[str, Any]:
    url = f"{api_base}/organizations/{organization_id}/projects/{project_id}/import/jobs/{job_id}/cancellation"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
