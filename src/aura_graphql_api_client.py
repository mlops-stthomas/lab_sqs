"""
Neo4j Aura GraphQL Data API Client

Programmatically create and manage GraphQL APIs on Aura instances.
Based on Aura API v1 GraphQL Data API endpoints.
"""
import os
import base64
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class AuthProviderType(Enum):
    """GraphQL API authentication provider types."""
    API_KEY = "api-key"
    JWKS = "jwks"


@dataclass
class AuthProvider:
    """GraphQL API authentication provider configuration."""
    name: str
    type: AuthProviderType
    url: Optional[str] = None  # Required for JWKS


@dataclass
class GraphQLAPI:
    """GraphQL Data API metadata."""
    id: str
    instance_id: str
    name: str
    endpoint: str
    api_key: Optional[str] = None
    introspection_enabled: bool = True
    field_suggestions_enabled: bool = True


class AuraGraphQLAPIClient:
    """
    Client for managing Neo4j Aura GraphQL Data APIs.

    Allows programmatic creation and management of GraphQL APIs
    with custom type definitions, authentication, and CORS policies.
    """

    API_BASE = "https://api.neo4j.io/v1"
    OAUTH_URL = "https://api.neo4j.io/oauth/token"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        """
        Initialize GraphQL API client.

        Args:
            client_id: Aura API client ID (uses AURA_API_CLIENT_ID env var if not provided)
            client_secret: Aura API client secret (uses AURA_API_CLIENT_SECRET env var if not provided)
        """
        self.client_id = client_id or os.getenv('AURA_API_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('AURA_API_CLIENT_SECRET')

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "client_id and client_secret are required. "
                "Set AURA_API_CLIENT_ID and AURA_API_CLIENT_SECRET environment variables."
            )

        self.access_token: Optional[str] = None
        self.token_expiry: float = 0

        logger.info("Aura GraphQL API client initialized")

    def _get_access_token(self) -> str:
        """Get valid OAuth 2.0 access token."""
        import time

        # Return cached token if still valid
        if self.access_token and time.time() < (self.token_expiry - 300):
            return self.access_token

        # Request new token using HTTP Basic Auth
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')

        response = requests.post(
            self.OAUTH_URL,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {auth_b64}'
            },
            data={'grant_type': 'client_credentials'}
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data['access_token']
        # Tokens expire after 1 hour (3600 seconds)
        import time
        self.token_expiry = time.time() + 3600

        if not self.access_token:
            raise RuntimeError("Failed to obtain access token from OAuth response")
        
        return self.access_token

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with current authentication token."""
        token = self._get_access_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

    def create_graphql_api(
        self,
        instance_id: str,
        name: str,
        type_definitions: str,
        auth_providers: List[AuthProvider],
        cors_origins: Optional[List[str]] = None,
        introspection_enabled: bool = False,
        field_suggestions_enabled: bool = False
    ) -> GraphQLAPI:
        """
        Create a new GraphQL Data API on an Aura instance.

        Args:
            instance_id: Target Aura instance ID
            name: Name for the GraphQL API
            type_definitions: GraphQL SDL type definitions (will be base64 encoded)
            auth_providers: List of authentication providers
            cors_origins: Allowed CORS origins (default: ["*"])
            introspection_enabled: Enable GraphQL introspection
            field_suggestions_enabled: Enable field suggestions

        Returns:
            GraphQLAPI object with endpoint and API key
        """
        if cors_origins is None:
            cors_origins = ["*"]

        # Encode type definitions to base64
        type_defs_b64 = base64.b64encode(type_definitions.encode('utf-8')).decode('utf-8')

        # Create the GraphQL API
        url = f"{self.API_BASE}/instances/{instance_id}/graphql"

        payload = {
            "name": name,
            "type_definitions": type_defs_b64,
            "enable_introspection": introspection_enabled,
            "enable_field_suggestions": field_suggestions_enabled
        }

        response = requests.post(
            url,
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()

        data = response.json()
        logger.info(f"GraphQL API create response: {data}")

        # Extract API details
        api_data = data.get('data', {})
        api_id = api_data.get('id')
        endpoint = api_data.get('endpoint')
        api_key = api_data.get('api_key')

        # Create GraphQL API object
        api = GraphQLAPI(
            id=api_id,
            instance_id=instance_id,
            name=name,
            endpoint=endpoint,
            api_key=api_key,
            introspection_enabled=introspection_enabled,
            field_suggestions_enabled=field_suggestions_enabled
        )

        # Add authentication providers
        for provider in auth_providers:
            self.add_auth_provider(instance_id, api_id, provider)

        # Add CORS origins
        for origin in cors_origins:
            self.add_cors_origin(instance_id, api_id, origin)

        logger.info(f"GraphQL API created: {api_id}")
        logger.info(f"Endpoint: {endpoint}")

        return api

    def add_auth_provider(
        self,
        instance_id: str,
        api_id: str,
        provider: AuthProvider
    ) -> Dict[str, Any]:
        """
        Add an authentication provider to a GraphQL API.

        Args:
            instance_id: Aura instance ID
            api_id: GraphQL API ID
            provider: Authentication provider configuration

        Returns:
            API response
        """
        url = f"{self.API_BASE}/data-api/graphql/auth-provider"

        payload = {
            "data_api_id": api_id,
            "instance_id": instance_id,
            "name": provider.name,
            "type": provider.type.value
        }

        if provider.type == AuthProviderType.JWKS and provider.url:
            payload["url"] = provider.url

        response = requests.post(
            url,
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()

        logger.info(f"Added auth provider '{provider.name}' to API {api_id}")
        return response.json()

    def add_cors_origin(
        self,
        instance_id: str,
        api_id: str,
        origin: str
    ) -> Dict[str, Any]:
        """
        Add a CORS origin to a GraphQL API.

        Args:
            instance_id: Aura instance ID
            api_id: GraphQL API ID
            origin: CORS origin (e.g., "https://example.com" or "*")

        Returns:
            API response
        """
        url = f"{self.API_BASE}/data-api/graphql/cors-policy/allowed-origin"

        payload = {
            "data_api_id": api_id,
            "instance_id": instance_id,
            "origin": origin
        }

        response = requests.post(
            url,
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()

        logger.info(f"Added CORS origin '{origin}' to API {api_id}")
        return response.json()

    def update_type_definitions(
        self,
        api_id: str,
        type_definitions: str
    ) -> Dict[str, Any]:
        """
        Update GraphQL type definitions for an existing API.

        Args:
            api_id: GraphQL API ID
            type_definitions: New GraphQL SDL type definitions

        Returns:
            API response
        """
        url = f"{self.API_BASE}/data-api/graphql/{api_id}"

        # Encode type definitions to base64
        type_defs_b64 = base64.b64encode(type_definitions.encode('utf-8')).decode('utf-8')

        payload = {
            "type_definitions": type_defs_b64
        }

        response = requests.patch(
            url,
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()

        logger.info(f"Updated type definitions for API {api_id}")
        return response.json()

    def delete_graphql_api(
        self,
        instance_id: str,
        api_id: str
    ) -> Dict[str, Any]:
        """
        Delete a GraphQL Data API.

        Args:
            instance_id: Aura instance ID
            api_id: GraphQL API ID

        Returns:
            API response
        """
        url = f"{self.API_BASE}/instances/{instance_id}/graphql/{api_id}"

        response = requests.delete(
            url,
            headers=self._get_headers()
        )
        response.raise_for_status()

        logger.info(f"Deleted GraphQL API {api_id}")
        return response.json()

    def get_graphql_api(
        self,
        instance_id: str,
        api_id: str
    ) -> GraphQLAPI:
        """
        Get details of a GraphQL Data API.

        Args:
            instance_id: Aura instance ID
            api_id: GraphQL API ID

        Returns:
            GraphQLAPI object
        """
        url = f"{self.API_BASE}/instances/{instance_id}/graphql/{api_id}"

        response = requests.get(
            url,
            headers=self._get_headers()
        )
        response.raise_for_status()

        data = response.json()
        api_data = data.get('data', {})

        return GraphQLAPI(
            id=api_data.get('id'),
            instance_id=instance_id,
            name=api_data.get('name'),
            endpoint=api_data.get('endpoint'),
            introspection_enabled=api_data.get('enable_introspection', False),
            field_suggestions_enabled=api_data.get('enable_field_suggestions', False)
        )


# Helper function to load type definitions from file
def load_type_definitions(file_path: str) -> str:
    """Load GraphQL type definitions from a file."""
    with open(file_path, 'r') as f:
        return f.read()
