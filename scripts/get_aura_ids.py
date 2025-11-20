#!/usr/bin/env python3
"""
Helper script to find your Aura Organization and Project IDs.

This script will help you locate the IDs you need for the Aura Import API.
"""
import webbrowser
import sys

print("="*60)
print("Finding Your Aura Organization and Project IDs")
print("="*60)

print("\n1. Opening Neo4j Aura Console...")
print("   URL: https://console.neo4j.io")

# Open browser
try:
    webbrowser.open("https://console.neo4j.io")
    print("   ✓ Browser opened")
except Exception as e:
    print(f"   ⚠ Could not open browser: {e}")
    print("   Please manually navigate to: https://console.neo4j.io")

print("\n2. To find your Organization ID:")
print("   - Click your profile icon (top right)")
print("   - Go to 'Account Settings'")
print("   - Copy the 'Organization ID' shown on the page")

print("\n3. To find your Project ID:")
print("   - Navigate to any project in Aura Console")
print("   - Check the URL, it will look like:")
print("     console.neo4j.io/projects/<YOUR-PROJECT-ID>/...")
print("   - Copy the UUID that appears after '/projects/'")

print("\n4. Once you have both IDs, update your .env file:")
print("   Edit: /Users/johnaffolter/snowflake_neo4j_pipeline/lab_sqs/.env")
print("   Uncomment and fill in:")
print("   AURA_ORGANIZATION_ID=<paste-org-id-here>")
print("   AURA_PROJECT_ID=<paste-project-id-here>")

print("\n5. After updating .env, test your setup:")
print("   python scripts/test_aura_setup.py")

print("\n" + "="*60)
print("Need help? Check: https://console.neo4j.io")
print("="*60)
