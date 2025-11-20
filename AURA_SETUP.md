# Neo4j Aura Integration Setup Guide

Complete setup and testing guide for the Aura CLI and Import API integration.

## Quick Start Checklist

- [x] Aura CLI installed (`aura-cli --version` shows v1.1.1)
- [x] Aura API credentials added to `.env`
- [ ] Organization ID and Project ID added to `.env`
- [ ] Test Aura Manager connection
- [ ] Create first import model in Aura Console
- [ ] Trigger test import job

---

## Step 1: Complete Environment Configuration

You've already added the Aura API credentials. Now add your Organization and Project IDs:

### Find Your IDs

1. Go to [https://console.neo4j.io](https://console.neo4j.io)
2. **Organization ID**:
   - Click your profile (top right)
   - Go to Account Settings
   - Copy the Organization ID
3. **Project ID**:
   - Navigate to any project
   - Check the URL: `console.neo4j.io/projects/<project-id>/...`
   - Copy the project ID from the URL

### Update .env

Edit `/Users/johnaffolter/snowflake_neo4j_pipeline/lab_sqs/.env`:

```bash
# Uncomment and fill in:
AURA_ORGANIZATION_ID=your-org-id-here
AURA_PROJECT_ID=your-project-id-here
```

---

## Step 2: Test Aura Manager

Once you've added the IDs, test the connection:

```bash
# From lab_sqs directory
cd /Users/johnaffolter/snowflake_neo4j_pipeline/lab_sqs

# Test Aura Manager
python src/aura_manager.py
```

**Expected output:**
```
=== Aura Health Check ===
{
  "cli": {"status": "healthy"},
  "instances": {
    "status": "healthy",
    "count": 3,
    "details": [...]
  },
  "graphql_apis": {"status": "healthy", "count": 0},
  "import_api": {
    "status": "healthy",
    "organization_id": "your-org-id"
  }
}

=== Aura Instances ===
ID           Name                           Tier                 Status
--------------------------------------------------------------------------------
705c1e42     melting-pot-kg                Professional         running
20d44169     proper-kg                     Professional         running
c37dd390     tray-kg                       Professional         running

=== GraphQL Data APIs ===
...

=== Aura Import API ===
✓ Import API configured for organization: your-org-id
```

---

## Step 3: Create Import Model in Aura Console

Before you can trigger imports programmatically, you need to create an import model via the Aura UI:

### 3.1 Create Data Source

1. Navigate to [Aura Console > Tools > Import](https://console.neo4j.io/tools/import)
2. Click **Create Data Source**
3. Select data source type:
   - **Snowflake** (recommended for your setup)
   - BigQuery
   - S3
   - PostgreSQL
   - MySQL

4. Configure Snowflake connection:
   ```
   Account: <from your Snowflake config>
   Warehouse: COMPUTE_WH
   Database: THE_MELTING_POT
   Schema: PUBLIC
   User: <your Snowflake user>
   Password: <your Snowflake password>
   ```

5. Test connection and save

### 3.2 Build Graph Model

1. Select your data source
2. Browse available tables (you should see Toast data tables)
3. Click **Create Model**
4. Use visual builder to map:
   - **Nodes**: Orders, Restaurants, Employees, MenuItems
   - **Relationships**: PLACED_AT, CREATED_BY, CONTAINS
   - **Properties**: Select relevant columns

5. **Set Unique Constraints** (critical for idempotent imports):
   - Order.guid
   - Restaurant.restaurantGuid
   - Employee.guid
   - MenuItem.guid

6. Test with sample data
7. Save the model

### 3.3 Note Import Model ID

After saving, you'll see the model in the Import dashboard. Click on it and copy the ID from the URL:

```
https://console.neo4j.io/tools/import/models/<COPY-THIS-ID>
```

Save this ID - you'll use it to trigger imports programmatically.

---

## Step 4: Test Import Job Trigger

Once you have an import model ID, test triggering an import job:

```bash
# Set your import model ID
export IMPORT_MODEL_ID="your-model-id-from-step-3"

# Set target instance (e.g., Melting Pot KG)
export INSTANCE_ID="705c1e42"

# Test with Python
python -c "
from src.aura_manager import AuraManager

manager = AuraManager()
manager.setup_import_client()

# Trigger import job
job = manager.create_import_job(
    import_model_id='$IMPORT_MODEL_ID',
    db_id='$INSTANCE_ID'
)

print(f'✓ Import job created: {job.id}')
print(f'  State: {job.state}')
print(f'  Type: {job.import_type}')
"
```

---

## Step 5: Monitor Import Job

Monitor the job you just created:

```bash
# Get the job ID from Step 4 output
export JOB_ID="your-job-id"

# Check status
python scripts/check_import_status.py --job-id $JOB_ID --progress

# Or watch until completion
python scripts/check_import_status.py --job-id $JOB_ID --watch
```

---

## Step 6: Set Up Automated Pipelines

### Incremental Hourly Sync

```bash
# Create incremental pipeline config
python scripts/setup_incremental_pipeline.py \
  --import-model-id $IMPORT_MODEL_ID \
  --instance-id 705c1e42 \
  --schedule "0 * * * *" \
  --name snowflake_melting_pot_hourly

# This creates:
# - config/import_pipelines.json (pipeline configuration)
# - Crontab entry (for scheduling)
# - Optional: Airflow DAG (with --generate-airflow-dag flag)
```

### Test Pipeline Execution

```bash
# Test run (doesn't actually trigger import)
python scripts/run_import_pipeline.py \
  --pipeline-name snowflake_melting_pot_hourly \
  --dry-run

# Actual run
python scripts/run_import_pipeline.py \
  --pipeline-name snowflake_melting_pot_hourly
```

### Schedule with Cron

```bash
# Edit crontab
crontab -e

# Add the entry shown by setup_incremental_pipeline.py:
# 0 * * * * cd /Users/johnaffolter/snowflake_neo4j_pipeline/lab_sqs && python scripts/run_import_pipeline.py --pipeline-name snowflake_melting_pot_hourly >> logs/import.log 2>&1
```

### Historical Onboarding

For one-time bulk import of historical data:

```bash
# Create a separate import model in Aura Console for historical data
# (configure to import all data, not just recent)

export HISTORICAL_MODEL_ID="your-historical-model-id"

# Run historical import with verification
python scripts/historical_import.py \
  --import-model-id $HISTORICAL_MODEL_ID \
  --instance-id 705c1e42 \
  --knowledge-graph melting-pot \
  --verify \
  --create-snapshot

# This will:
# - Create snapshot (for rollback)
# - Collect pre-import stats
# - Trigger import job
# - Wait for completion
# - Verify results
# - Generate report
```

---

## Available Scripts

All scripts are in the `scripts/` directory:

| Script | Purpose |
|--------|---------|
| `setup_incremental_pipeline.py` | Configure automated pipelines |
| `run_import_pipeline.py` | Execute configured pipelines |
| `historical_import.py` | One-time bulk import with verification |
| `check_import_status.py` | Monitor import job progress |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│            Aura Manager (Python)                    │
│  - CLI wrapper (instance/GraphQL API management)    │
│  - Import API client (job orchestration)            │
│  - Multi-instance connector (Neo4j queries)         │
└────────────┬────────────────────────────────────────┘
             │
    ┌────────┼────────┬──────────────────┐
    │        │        │                  │
    ▼        ▼        ▼                  ▼
┌────────┐ ┌───────┐ ┌──────────────┐  ┌──────────┐
│Aura CLI│ │Import │ │Neo4j Driver  │  │Snowflake │
│v1.1.1  │ │API    │ │(3 instances) │  │Connector │
└────────┘ │v2beta1│ └──────────────┘  └──────────┘
           └───┬───┘
               │
         ┌─────┴──────────┐
         │                │
    ┌────▼─────┐    ┌─────▼────┐
    │  Data    │    │  Aura    │
    │  Sources │    │  Console │
    │          │    │  (UI)    │
    │-Snowflake│    └──────────┘
    │-BigQuery │
    │-S3       │
    └──────────┘
```

---

## Troubleshooting

### "Import client not initialized"

**Fix**: Call `manager.setup_import_client()` before using import methods

```python
manager = AuraManager()
manager.setup_import_client()  # Required!
manager.create_import_job(...)
```

### "Configuration missing"

**Fix**: Ensure all 4 environment variables are set:
- `AURA_API_CLIENT_ID`
- `AURA_API_CLIENT_SECRET`
- `AURA_ORGANIZATION_ID`
- `AURA_PROJECT_ID`

### "Import job failed: Schema validation error"

**Fix**:
1. Check import model in Aura Console
2. Verify table names match your Snowflake schema
3. Refresh data source if tables changed
4. Test model with sample data before running full import

### "Duplicate nodes created"

**Fix**:
1. Go to import model settings
2. Add unique constraints on ID fields
3. Re-run import (existing nodes will be updated, not duplicated)

---

## Next Steps

1. ✅ Complete `.env` configuration (Organization ID, Project ID)
2. ✅ Test Aura Manager health check
3. ✅ Create first import model in Aura Console
4. ✅ Trigger test import job
5. ✅ Set up incremental pipeline for hourly syncs
6. ✅ Run historical onboarding for existing data
7. 🔄 Integrate with Airflow for orchestration
8. 🔄 Add monitoring and alerting
9. 🔄 Document data lineage in Neo4j

---

## Resources

- [Neo4j Aura Console](https://console.neo4j.io)
- [Aura Import API Docs](https://neo4j.com/docs/aura/platform/api/specification/)
- [Aura CLI Docs](https://neo4j.com/labs/aura-cli/)
- [Import Service Guide](https://neo4j.com/docs/aura/import/quick-start/)

---

**Questions?** All code is ready to use. Just complete the `.env` configuration and follow the steps above.
