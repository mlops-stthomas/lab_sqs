# Quick Start: Get Data Importer Running

Step-by-step guide to get your Aura Import API working and investigate your data.

---

## Step 1: Get Your Aura IDs (5 minutes)

Run the helper script:

```bash
python scripts/get_aura_ids.py
```

This will:
1. Open the Aura Console in your browser
2. Guide you to find your Organization ID and Project ID
3. Tell you exactly where to add them in `.env`

**Manual steps:**

1. Go to [console.neo4j.io](https://console.neo4j.io)
2. **Organization ID**:
   - Click profile icon (top right)
   - Account Settings
   - Copy Organization ID
3. **Project ID**:
   - Navigate to any project
   - Check URL: `console.neo4j.io/projects/<PROJECT-ID>/...`
   - Copy the UUID

4. Update `.env`:
   ```bash
   # Uncomment and fill in:
   AURA_ORGANIZATION_ID=paste-your-org-id-here
   AURA_PROJECT_ID=paste-your-project-id-here
   ```

---

## Step 2: Test Your Setup (2 minutes)

Run the comprehensive test suite:

```bash
python scripts/test_aura_setup.py
```

**Expected output:**
```
✓ Environment Variables: PASSED
✓ Aura CLI: PASSED
✓ Aura Manager Initialization: PASSED
✓ Health Check: PASSED
✓ List Instances: PASSED
✓ Import API Authentication: PASSED
🎉 All tests passed!
```

If any tests fail, check:
- `.env` has all 4 Aura variables set
- Organization and Project IDs are correct
- Aura CLI is installed (`aura-cli --version`)

---

## Step 3: Investigate Your Data (5 minutes)

Explore what's already in your knowledge graphs:

```bash
# Investigate all knowledge graphs
python scripts/investigate_aura_data.py

# Or investigate specific one
python scripts/investigate_aura_data.py --kg melting-pot
```

**This shows you:**
- 📊 Total nodes and relationships
- 📦 Node label distribution
- 🔗 Relationship types
- 📅 Data freshness (most recent orders)
- 🏪 Restaurant count and names
- 👥 Employee count
- 🔍 Vector index status (for Aura Agent)
- 💡 Import opportunities

**Example output:**
```
📊 Overview:
  Total Nodes: 1,228,103
  Total Relationships: 2,603,272
  Node Labels: 15
  Relationship Types: 20

📦 Top Node Labels:
  Order                          850,000 nodes
  MenuItem                       250,000 nodes
  Employee                         3,816 nodes
  Restaurant                          80 nodes

📅 Data Freshness (Orders):
  Latest Order: 2025-11-19T08:30:00Z
  Orders Today: 1,250

💡 Import Opportunities:
  - Order data is >1 day old - consider daily imports
```

---

## Step 4: Create Your First Import Model (10-15 minutes)

Now that you know what data you have, create an import model in Aura Console:

### 4.1 Navigate to Import Tool

1. Go to [console.neo4j.io/tools/import](https://console.neo4j.io/tools/import)
2. Click **Create Data Source**

### 4.2 Configure Snowflake Data Source

Based on your investigation, choose the data you want to import:

**For Toast Orders (Daily/Hourly Updates):**
```
Data Source Type: Snowflake
Account: <from your Snowflake config>
Warehouse: COMPUTE_WH
Database: THE_MELTING_POT
Schema: PUBLIC
Table: THE_MELTING_POT_TOAST_ORDERS_BULK
```

Add a WHERE clause for incremental imports:
```sql
WHERE business_date >= CURRENT_DATE - INTERVAL '2 days'
```

### 4.3 Build Graph Model

Click **Create Model** and map your data:

**Nodes:**
- `Order` - From TOAST_ORDERS_BULK
  - Set unique constraint on `guid`
  - Properties: displayNumber, businessDate, totalAmount, etc.

- `Restaurant` - From TOAST_RESTAURANTS
  - Set unique constraint on `restaurantGuid`
  - Properties: restaurantName, locationName

**Relationships:**
- `(Order)-[:PLACED_AT]->(Restaurant)`
  - Join on: TOAST_ORDERS_BULK.restaurantGuid = TOAST_RESTAURANTS.restaurantGuid

### 4.4 Test and Save

1. Click **Test Import** with sample data
2. Verify results in preview
3. **Save** the model
4. **Copy the Import Model ID** from the URL:
   ```
   https://console.neo4j.io/tools/import/models/<COPY-THIS-ID>
   ```

---

## Step 5: Trigger Your First Import (5 minutes)

Now use the API to trigger an import:

```bash
# Set your IDs
export IMPORT_MODEL_ID="paste-model-id-from-step-4"
export INSTANCE_ID="705c1e42"  # Use ID from investigate_aura_data.py

# Test with Python
python -c "
from src.aura_manager import AuraManager

manager = AuraManager()
manager.setup_import_client()

# Trigger import
job = manager.create_import_job(
    import_model_id='$IMPORT_MODEL_ID',
    db_id='$INSTANCE_ID'
)

print(f'✓ Import job created: {job.id}')
print(f'  State: {job.state}')
print(f'  Type: {job.import_type}')
print()
print(f'Monitor with:')
print(f'python scripts/check_import_status.py --job-id {job.id} --watch')
"
```

### Monitor the Job

```bash
# Get job ID from above output, then:
python scripts/check_import_status.py --job-id <job-id> --watch
```

**Expected output:**
```
============================================================
Import Job Status
============================================================
Job ID: 667a9266-07bc-48a0-ae5f-3d1e8e73fac4
State: Running
Type: cloud
Progress: 45%

Nodes Processed:
  Order: 1,250/2,500 rows (1,200 created)
  Restaurant: 80/80 rows (0 created - already exist)

Next check in 30s... (Ctrl+C to stop)
```

---

## Step 6: Set Up Automated Pipeline (10 minutes)

Once your test import succeeds, automate it:

```bash
# Configure hourly incremental sync
python scripts/setup_incremental_pipeline.py \
  --import-model-id $IMPORT_MODEL_ID \
  --instance-id $INSTANCE_ID \
  --schedule "0 * * * *" \
  --name melting_pot_hourly_sync

# This creates:
# - config/import_pipelines.json (pipeline config)
# - Crontab entry for scheduling
```

**Test the pipeline:**

```bash
# Dry run (doesn't actually import)
python scripts/run_import_pipeline.py \
  --pipeline-name melting_pot_hourly_sync \
  --dry-run

# Actual run
python scripts/run_import_pipeline.py \
  --pipeline-name melting_pot_hourly_sync
```

**Schedule with cron:**

```bash
# Edit crontab
crontab -e

# Add the generated entry (shown by setup_incremental_pipeline.py)
# Example:
0 * * * * cd /Users/johnaffolter/snowflake_neo4j_pipeline/lab_sqs && python scripts/run_import_pipeline.py --pipeline-name melting_pot_hourly_sync >> logs/import.log 2>&1
```

---

## Step 7: Verify Import Results (5 minutes)

After your import completes, verify in Neo4j Browser:

1. Open Neo4j Browser: [console.neo4j.io](https://console.neo4j.io)
2. Connect to your instance
3. Run verification queries:

```cypher
// Check total orders
MATCH (o:Order)
RETURN count(o) as total_orders

// Check today's orders
MATCH (o:Order)
WHERE date(o.createdAt) = date()
RETURN count(o) as today_orders

// Check restaurants with most orders
MATCH (r:Restaurant)<-[:PLACED_AT]-(o:Order)
RETURN r.restaurantName, count(o) as order_count
ORDER BY order_count DESC
LIMIT 10

// Verify no duplicates (guid should be unique)
MATCH (o:Order)
WITH o.guid as guid, count(*) as cnt
WHERE cnt > 1
RETURN guid, cnt
// Should return 0 rows if unique constraints work
```

---

## Troubleshooting

### "Environment variables not set"

```bash
# Check all 4 Aura variables are in .env:
cat .env | grep AURA_

# Should show:
# AURA_API_CLIENT_ID=MPGDSjrdi1iYhpcFGkmua1LKkTCEMjPx
# AURA_API_CLIENT_SECRET=LnaIH0C2BSUxTlXTnrBdZsR0Tbgxi6bbJTA8clk7wlZKe0TAmhmIOmaZuIO1FyYj
# AURA_ORGANIZATION_ID=your-org-id
# AURA_PROJECT_ID=your-project-id
```

### "Import job failed: Schema validation error"

1. Check table names in import model match Snowflake
2. Refresh data source if tables changed
3. Test model with sample data first

### "Duplicate nodes created"

1. Go to import model settings
2. Add unique constraint on ID field (e.g., `guid`)
3. Re-run import - duplicates will be merged

### "No instances found"

Check Organization and Project IDs are correct:
```bash
# Test with Aura CLI
aura-cli instance list --output json
```

---

## Next Steps

✅ **You're now importing data programmatically!**

### Immediate

1. Set up daily/hourly incremental syncs
2. Create import models for other data (Employees, MenuItems)
3. Monitor first scheduled import

### Short Term

4. Run historical onboarding for existing data:
   ```bash
   python scripts/historical_import.py \
     --import-model-id <historical-model-id> \
     --instance-id $INSTANCE_ID \
     --verify \
     --create-snapshot
   ```

5. Verify data quality and completeness

### Medium Term

6. Create **Aura Agent** for restaurant operations
7. Integrate with Airflow for orchestration
8. Add monitoring and alerting
9. Implement GEPA optimization for Cypher generation

---

## Resources

- **Aura Console**: https://console.neo4j.io
- **Import API Docs**: https://neo4j.com/docs/aura/platform/api/specification/
- **Full Setup Guide**: [AURA_SETUP.md](AURA_SETUP.md)
- **Architecture**: [README.md](README.md)

---

**Questions?** Run `python scripts/test_aura_setup.py` to verify your setup anytime!
