# Aura CLI and Import API Demonstration Summary

**Date**: 2025-11-19
**Instance**: melting-pot-kg (705c1e42)
**Import Model**: e4cd23ef-c4ec-4e27-8d5d-0e890f496388

---

## What we demonstrated

### 1. Aura CLI capabilities

```bash
# List all instances
aura-cli instance list --output json

# Found 5 instances:
- proper-kg (20d44169)
- melting-pot-kg (705c1e42)  ← Used for demo
- genetica-free (b9721672)
- tray-kg (c37dd390)
- Instance01 (fe60573a)
```

**Available Aura CLI commands**:
- `instance` - Create, delete, list, pause, resume, snapshot, update instances
- `data-api` - Manage GraphQL Data APIs
- `config` - Manage configuration values
- `credential` - Manage credentials
- `tenant` - Tenant management

**Important**: Import jobs are NOT managed through the CLI - they're managed through the **Aura Import API** (REST API).

---

### 2. Aura Import API integration

#### Test suite results

```bash
python scripts/test_aura_setup.py
```

**Results**: All 8 tests passed ✅
- Environment Variables: PASSED
- Aura CLI: PASSED (v1.1.1, beta enabled)
- Aura Manager Initialization: PASSED
- Health Check: PASSED
- List Instances: PASSED (5 instances found)
- List GraphQL APIs: PASSED
- Import API Authentication: PASSED (OAuth 2.0 token obtained)
- Import Job Dry Run: PASSED

---

### 3. Import job creation

```bash
python scripts/test_import_model.py \
  --import-model-id e4cd23ef-c4ec-4e27-8d5d-0e890f496388 \
  --instance-id 705c1e42 \
  --no-wait
```

**Job created**: `da0f5f37-ac63-48d0-93ab-fae04ff3edcd`

**API request**:
```json
POST /v2beta1/organizations/{org_id}/projects/{project_id}/import/jobs
{
  "importModelId": "e4cd23ef-c4ec-4e27-8d5d-0e890f496388",
  "auraCredentials": {
    "dbId": "705c1e42"
  }
}
```

**API response**:
```json
{
  "data": {
    "id": "da0f5f37-ac63-48d0-93ab-fae04ff3edcd"
  }
}
```

---

### 4. Import job monitoring

```bash
python scripts/check_import_status.py \
  --job-id da0f5f37-ac63-48d0-93ab-fae04ff3edcd \
  --progress
```

**Full job details**:
```json
{
  "data": {
    "id": "da0f5f37-ac63-48d0-93ab-fae04ff3edcd",
    "import_type": "cloud",
    "info": {
      "state": "Completed",
      "completion_time": "2025-11-20T05:13:13Z",
      "exit_status": {
        "state": "Failure",
        "message": "Aura instance is used in another import"
      },
      "submitted_time": "2025-11-20T05:13:13.053638Z",
      "last_update_time": "2025-11-20T05:13:34.793288Z",
      "percentage_complete": 100
    },
    "data_source": {
      "id": "d81f03af-89b5-4237-b167-03e8421b604d",
      "type": "snowflake-jwt",
      "name": "TRAY"
    },
    "aura_target": {
      "db_id": "705c1e42",
      "project_id": "e80cbffd-e13d-4f3e-9af2-4f8777fe4265"
    }
  }
}
```

**Result**: Job completed quickly with failure - instance was already being used by another import.

---

## Available API operations

### Supported operations

1. **Create import job**: `POST /import/jobs`
2. **Get job status**: `GET /import/jobs/{job_id}`
3. **Get job progress**: `GET /import/jobs/{job_id}?progress=true`
4. **Cancel job**: `POST /import/jobs/{job_id}/cancellation`

### Unsupported operations

- **List all jobs**: `GET /import/jobs` returns 405 Method Not Allowed
- Must track job IDs manually or use external database

---

## Python API wrapper usage

```python
from src.aura_manager import AuraManager

# Initialize manager
manager = AuraManager()
manager.setup_import_client()

# Create import job
job = manager.create_import_job(
    import_model_id='e4cd23ef-c4ec-4e27-8d5d-0e890f496388',
    db_id='705c1e42'
)
print(f'Job ID: {job.id}')
print(f'State: {job.state}')

# Monitor job
job = manager.get_import_job(job.id, include_progress=True)
print(f'Progress: {job.progress.percentage_complete}%')

# Wait for completion
final_job = manager.wait_for_import_completion(
    job.id,
    poll_interval=30,
    max_wait=1800
)
```

---

## Scripts available

### Testing and setup

- `scripts/test_aura_setup.py` - Comprehensive test suite
- `scripts/get_aura_ids.py` - Helper to find Org/Project IDs
- `scripts/investigate_aura_data.py` - Explore existing data (requires Neo4j creds)

### Import operations

- `scripts/test_import_model.py` - Trigger import job
- `scripts/check_import_status.py` - Monitor job status
- `scripts/setup_incremental_pipeline.py` - Configure automated pipelines
- `scripts/run_import_pipeline.py` - Execute configured pipelines
- `scripts/historical_import.py` - One-time bulk imports
- `scripts/orchestrate_hybrid_import.py` - Combine Snowflake + Aura Import

---

## Authentication flow

### OAuth 2.0 client credentials grant

1. **Encode credentials**: Base64(client_id:client_secret)
2. **Request token**:
   ```
   POST https://api.neo4j.io/oauth/token
   Authorization: Basic {base64_credentials}
   Content-Type: application/x-www-form-urlencoded

   grant_type=client_credentials
   ```
3. **Receive token**: Access token valid for 1 hour
4. **Use token**: `Authorization: Bearer {access_token}` in all API requests

**Token caching**: Automatically cached and refreshed 5 minutes before expiry

---

## Common import errors

### "Aura instance is used in another import"

**Cause**: Only one import job can run per instance at a time

**Solution**:
- Wait for current import to complete
- Check job status to find running imports
- Use different instance for parallel imports

### "Import model not found"

**Cause**: Invalid import model ID

**Solution**:
- Verify import model exists in Aura Console
- Copy ID from URL: `console.neo4j.io/tools/import/models/{MODEL_ID}`

### "Authentication failed"

**Cause**: Invalid credentials or expired token

**Solution**:
- Verify AURA_API_CLIENT_ID and AURA_API_CLIENT_SECRET in .env
- Check Organization ID and Project ID match
- Ensure credentials have Import API access

---

## Next steps

### Immediate

1. Wait for current import to complete on melting-pot-kg
2. Re-run test import to see successful completion
3. Monitor import progress with detailed logging

### Short term

4. Set up automated hourly pipelines
5. Configure incremental syncs with time-based filters
6. Add error notifications and retry logic

### Medium term

7. Create additional import models for other data sources
8. Implement hybrid approach (Snowflake procedures + Aura Import)
9. Build monitoring dashboard for all import jobs
10. Integrate with Airflow for orchestration

---

## Resources

- **Aura Console**: https://console.neo4j.io
- **Import Models**: https://console.neo4j.io/tools/import
- **API Spec**: https://neo4j.com/docs/aura/platform/api/specification/
- **CLI Docs**: https://neo4j.com/docs/aura/platform/api/aura-cli/
- **Import API Guide**: https://neo4j.com/blog/aura-cli-import-jobs/

---

**Configuration**:
- Organization ID: `e80cbffd-e13d-4f3e-9af2-4f8777fe4265`
- Project ID: `e80cbffd-e13d-4f3e-9af2-4f8777fe4265`
- Client: AURA_KEY_APRIL
