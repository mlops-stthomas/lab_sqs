#!/usr/bin/env python3
"""
Deploy Multi-Tenant GraphQL API to Aura instance.

This script creates a GraphQL Data API with authentication and authorization
for multi-tenant restaurant intelligence.

Usage:
    python scripts/deploy_graphql_api.py \
        --instance-id 705c1e42 \
        --name "Multi-Tenant Restaurant API" \
        --auth0-domain your-domain.auth0.com \
        --cors-origins "https://app.example.com,https://dashboard.example.com"
"""
import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aura_graphql_api_client import (
    AuraGraphQLAPIClient,
    AuthProvider,
    AuthProviderType,
    load_type_definitions
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def deploy_graphql_api(
    instance_id: str,
    name: str,
    auth0_domain: str = None,
    cors_origins: list[str] = None,
    introspection_enabled: bool = False,
    schema_file: str = None
):
    """
    Deploy multi-tenant GraphQL API to Aura instance.

    Args:
        instance_id: Target Aura instance ID
        name: Name for the GraphQL API
        auth0_domain: Auth0 domain for JWKS authentication
        cors_origins: List of allowed CORS origins
        introspection_enabled: Enable GraphQL introspection (disable in production)
        schema_file: Path to GraphQL schema file
    """
    logger.info("="*60)
    logger.info("Deploying Multi-Tenant GraphQL API")
    logger.info("="*60)
    logger.info(f"Instance ID: {instance_id}")
    logger.info(f"API Name: {name}")

    # Initialize client
    try:
        client = AuraGraphQLAPIClient()
        logger.info("✓ GraphQL API client initialized")
    except Exception as e:
        logger.error(f"✗ Failed to initialize client: {e}")
        sys.exit(1)

    # Load type definitions
    if not schema_file:
        schema_file = Path(__file__).parent.parent / "schemas" / "multi_tenant_restaurant_schema.graphql"

    try:
        type_definitions = load_type_definitions(str(schema_file))
        logger.info(f"✓ Loaded schema from {schema_file}")
        logger.info(f"  Schema size: {len(type_definitions)} characters")
    except Exception as e:
        logger.error(f"✗ Failed to load schema: {e}")
        sys.exit(1)

    # Configure authentication providers
    auth_providers = []

    # Add JWKS provider if Auth0 domain specified
    if auth0_domain:
        jwks_url = f"https://{auth0_domain}/.well-known/jwks.json"
        auth_providers.append(AuthProvider(
            name="Auth0 JWKS",
            type=AuthProviderType.JWKS,
            url=jwks_url
        ))
        logger.info(f"✓ Configured Auth0 JWKS: {jwks_url}")

    # Add API key provider
    auth_providers.append(AuthProvider(
        name="Admin API Key",
        type=AuthProviderType.API_KEY
    ))
    logger.info("✓ Configured API Key authentication")

    # Configure CORS origins
    if not cors_origins:
        cors_origins = ["*"]
        logger.warning("⚠ CORS set to allow all origins (*)")
        logger.warning("  Consider restricting to specific domains in production")
    else:
        logger.info(f"✓ CORS origins: {', '.join(cors_origins)}")

    # Create GraphQL API
    try:
        logger.info("\nCreating GraphQL API...")

        api = client.create_graphql_api(
            instance_id=instance_id,
            name=name,
            type_definitions=type_definitions,
            auth_providers=auth_providers,
            cors_origins=cors_origins,
            introspection_enabled=introspection_enabled,
            field_suggestions_enabled=False
        )

        logger.info("\n" + "="*60)
        logger.info("✓ GraphQL API Deployed Successfully!")
        logger.info("="*60)
        logger.info(f"API ID: {api.id}")
        logger.info(f"Endpoint: {api.endpoint}")

        if api.api_key:
            logger.info(f"\n⚠️  IMPORTANT: Save your API key securely!")
            logger.info(f"API Key: {api.api_key}")
            logger.info(f"\nThis API key will not be shown again.")

        logger.info("\n" + "="*60)
        logger.info("Next Steps")
        logger.info("="*60)
        logger.info("1. Test the API endpoint:")
        logger.info(f"   curl -X POST {api.endpoint} \\")
        logger.info(f"     -H 'x-api-key: YOUR_API_KEY' \\")
        logger.info(f"     -H 'Content-Type: application/json' \\")
        logger.info(f"     -d '{{\"query\": \"{{ __schema {{ queryType {{ name }} }} }}\"  }}'")
        logger.info("\n2. Configure your frontend to use this endpoint")
        logger.info("\n3. Set up JWT authentication with Auth0")
        logger.info("\n4. Test tenant-scoped queries")

        return api

    except Exception as e:
        logger.exception(f"\n✗ Failed to deploy GraphQL API: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy multi-tenant GraphQL API to Aura"
    )
    parser.add_argument(
        "--instance-id",
        required=True,
        help="Target Aura instance ID"
    )
    parser.add_argument(
        "--name",
        default="Multi-Tenant Restaurant API",
        help="Name for the GraphQL API"
    )
    parser.add_argument(
        "--auth0-domain",
        help="Auth0 domain for JWKS authentication (e.g., your-tenant.auth0.com)"
    )
    parser.add_argument(
        "--cors-origins",
        help="Comma-separated list of allowed CORS origins"
    )
    parser.add_argument(
        "--schema-file",
        help="Path to GraphQL schema file (default: schemas/multi_tenant_restaurant_schema.graphql)"
    )
    parser.add_argument(
        "--enable-introspection",
        action="store_true",
        help="Enable GraphQL introspection (not recommended for production)"
    )

    args = parser.parse_args()

    # Parse CORS origins
    cors_origins = None
    if args.cors_origins:
        cors_origins = [origin.strip() for origin in args.cors_origins.split(',')]

    # Deploy
    deploy_graphql_api(
        instance_id=args.instance_id,
        name=args.name,
        auth0_domain=args.auth0_domain,
        cors_origins=cors_origins,
        introspection_enabled=args.enable_introspection,
        schema_file=args.schema_file
    )


if __name__ == "__main__":
    main()
