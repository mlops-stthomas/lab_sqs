# Quick Reference: Aura Import API

One-page reference for common operations.

---

## Setup (one-time)

```bash
# 1. Test your setup
python scripts/test_aura_setup.py

# 2. Get your Organization/Project IDs (if needed)
python scripts/get_aura_ids.py

# 3. Create import model in Aura Console
# https://console.neo4j.io/tools/import
# Copy model ID from URL
```

---

## Trigger import job

```bash
# Option 1: Using Python script
python scripts/test_import_model.py \
  --import-model-id <MODEL_ID> \
  --instance-id <INSTANCE_ID>

# Option 2: Using Python directly
python -c "
from src.aura_manager import AuraManager

manager = AuraManager()
manager.setup_import_client()

job = manager.create_import_job(
    import_model_id='<MODEL_ID>',
    db_id='<INSTANCE_ID>'
)

print(f'Job ID: {job.id}')
print(f'State: {job.state}')
"
```

---

## Monitor import job

```bash
# Check status once
python scripts/check_import_status.py --job-id <JOB_ID>

# Watch continuously
python scripts/check_import_status.py --job-id <JOB_ID> --watch

# Get detailed progress
python scripts/check_import_status.py --job-id <JOB_ID> --progress
```

---

## List instances

```bash
# Using Aura CLI
aura-cli instance list --output json

# Using Python
python -c "
from src.aura_manager import AuraManager

manager = AuraManager()
instances = manager.list_instances()

for inst in instances:
    print(f'{inst.name}: {inst.id}')
"
```

---

## Common patterns

### Daily incremental sync
```bash
# 1. Create pipeline config
python scripts/setup_incremental_pipeline.py \
  --import-model-id <MODEL_ID> \
  --instance-id <INSTANCE_ID> \
  --schedule "0 2 * * *" \
  --name daily_sync

# 2. Add to crontab
crontab -e
# Add: 0 2 * * * cd /path/to/project && python scripts/run_import_pipeline.py --pipeline-name daily_sync
```

### Historical onboarding
```bash
python scripts/historical_import.py \
  --import-model-id <HISTORICAL_MODEL_ID> \
  --instance-id <INSTANCE_ID> \
  --verify \
  --create-snapshot
```

### Wait for completion
```python
from src.aura_manager import AuraManager

manager = AuraManager()
manager.setup_import_client()

job = manager.create_import_job(
    import_model_id='...',
    db_id='...'
)

# Wait with progress callback
final_job = manager.wait_for_import_completion(
    job.id,
    poll_interval=30,
    callback=lambda j: print(f'{j.state}: {j.progress.percentage_complete}%')
)
```

---

## Your instances

```
melting-pot-kg:  705c1e42
proper-kg:       20d44169
tray-kg:         c37dd390
genetica-free:   b9721672
Instance01:      fe60573a
```

---

## Your import model

```
Model ID: e4cd23ef-c4ec-4e27-8d5d-0e890f496388
Data Source: TRAY (Snowflake JWT)
```

---

## Troubleshooting

**"Instance is used in another import"**
→ Only 1 import per instance at a time
→ Wait for current job to complete

**"Authentication failed"**
→ Check credentials in .env
→ Verify Organization/Project IDs match

**"Import model not found"**
→ Verify model ID from Aura Console URL
→ Check model exists and is in same project

---

## API endpoints

```
Base: https://api.neo4j.io/v2beta1

POST /organizations/{org}/projects/{proj}/import/jobs
GET  /organizations/{org}/projects/{proj}/import/jobs/{job_id}
GET  /organizations/{org}/projects/{proj}/import/jobs/{job_id}?progress=true
POST /organizations/{org}/projects/{proj}/import/jobs/{job_id}/cancellation
```

---

## Environment variables

```bash
AURA_API_CLIENT_ID=MPGDSjrdi1iYhpcFGkmua1LKkTCEMjPx
AURA_API_CLIENT_SECRET=LnaIH0C2BSUxTlXTnrBdZsR0Tbgxi6bbJTA8clk7wlZKe0TAmhmIOmaZuIO1FyYj
AURA_ORGANIZATION_ID=e80cbffd-e13d-4f3e-9af2-4f8777fe4265
AURA_PROJECT_ID=e80cbffd-e13d-4f3e-9af2-4f8777fe4265
```

---

## Resources

- Aura Console: https://console.neo4j.io
- Import Tool: https://console.neo4j.io/tools/import
- API Docs: https://neo4j.com/docs/aura/platform/api/specification/
