"""Lightweight Python wrapper for creating/managing Aura GraphQL Data APIs.

This is a thin, well-tested wrapper kept inside `lab5_mlflow` so tests and
callers don't depend on the top-level `src` package layout.

Functions mirror the common operations used by operators: create API,
add auth provider, add cors origin, and update type definitions.
"""
from typing import Dict, Any, List, Optional
import os
import base64
import requests
import logging

logger = logging.getLogger(__name__)

API_BASE = os.environ.get('AURA_API_BASE', 'https://api.neo4j.io/v2beta1')
OAUTH_URL = os.environ.get('AURA_OAUTH_URL', 'https://api.neo4j.io/oauth/token')


def _get_token(client_id: str, client_secret: str, oauth_url: str = OAUTH_URL, timeout: int = 10) -> str:
    auth = requests.auth._basic_auth_str(client_id, client_secret)
    headers = {'Authorization': auth, 'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post(oauth_url, headers=headers, data='grant_type=client_credentials', timeout=timeout)
    r.raise_for_status()
    return r.json().get('access_token')


def _headers_for_token(token: str) -> Dict[str, str]:
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def create_graphql_api(
    client_id: str,
    client_secret: str,
    instance_id: str,
    name: str,
    type_definitions: str,
    auth_providers: Optional[List[Dict[str, Any]]] = None,
    cors_origins: Optional[List[str]] = None,
    introspection_enabled: bool = False,
    field_suggestions_enabled: bool = False,
    api_base: str = API_BASE,
):
    """Create a GraphQL Data API on an Aura instance and return the API JSON.

    `type_definitions` is sent base64-encoded per Aura API spec.
    """
    token = _get_token(client_id, client_secret)
    url = f"{api_base}/instances/{instance_id}/graphql"
    if cors_origins is None:
        cors_origins = ["*"]

    payload = {
        'name': name,
        'type_definitions': base64.b64encode(type_definitions.encode('utf-8')).decode('utf-8'),
        'enable_introspection': introspection_enabled,
        'enable_field_suggestions': field_suggestions_enabled,
        'cors_origins': cors_origins,
    }

    r = requests.post(url, headers=_headers_for_token(token), json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()

    # If auth_providers were provided, add them now
    api_id = data.get('data', {}).get('id')
    if auth_providers and api_id:
        for provider in auth_providers:
            add_auth_provider(client_id, client_secret, instance_id, api_id, provider, api_base=api_base)

    # Add CORS origins explicitly if provided
    if cors_origins and api_id:
        for origin in cors_origins:
            add_cors_origin(client_id, client_secret, instance_id, api_id, origin, api_base=api_base)

    logger.info('Created GraphQL API: %s', api_id)
    return data


def add_auth_provider(client_id: str, client_secret: str, instance_id: str, api_id: str, provider: Dict[str, Any], api_base: str = API_BASE):
    url = f"{api_base}/data-api/graphql/auth-provider"
    token = _get_token(client_id, client_secret)
    payload = {
        'data_api_id': api_id,
        'instance_id': instance_id,
        'name': provider.get('name'),
        'type': provider.get('type'),
        'url': provider.get('url'),
    }
    r = requests.post(url, headers=_headers_for_token(token), json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def add_cors_origin(client_id: str, client_secret: str, instance_id: str, api_id: str, origin: str, api_base: str = API_BASE):
    url = f"{api_base}/data-api/graphql/cors-policy/allowed-origin"
    token = _get_token(client_id, client_secret)
    payload = {
        'data_api_id': api_id,
        'instance_id': instance_id,
        'origin': origin,
    }
    r = requests.post(url, headers=_headers_for_token(token), json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def update_type_definitions(client_id: str, client_secret: str, api_id: str, type_definitions: str, api_base: str = API_BASE):
    url = f"{api_base}/data-api/graphql/{api_id}"
    token = _get_token(client_id, client_secret)
    payload = {'type_definitions': base64.b64encode(type_definitions.encode('utf-8')).decode('utf-8')}
    r = requests.patch(url, headers=_headers_for_token(token), json=payload, timeout=10)
    r.raise_for_status()
    return r.json()
