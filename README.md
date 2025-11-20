# Neo4j Aura Import & SQS Integration

Comprehensive data pipeline and ingestion system combining:
- **Neo4j Aura Import API** - Programmatic data loading from Snowflake/BigQuery/S3
- **Aura CLI Integration** - Instance and GraphQL API management
- **AWS SQS** - Message queue for async job processing
- **Automated Pipelines** - Hourly incremental syncs and historical onboarding
- **GPT-5 Responses API** - Context-Free Grammar for Cypher generation

---

## Project Structure

```
lab_sqs/
├── src/
│   ├── aura_manager.py              # Unified Aura management (CLI + API)
│   ├── consumer.py                  # SQS message consumer
│   ├── msg_writer.py                # SQS message writer
│   ├── writer.py                    # Message writer utilities
│   └── settings.py                  # Configuration management
│
├── scripts/
│   ├── setup_incremental_pipeline.py    # Configure automated pipelines
│   ├── run_import_pipeline.py           # Execute configured pipelines
│   ├── historical_import.py             # One-time bulk import
│   ├── check_import_status.py           # Monitor import jobs
│   └── test_aura_setup.py               # Comprehensive test suite
│
├── lab5_mlflow/
│   ├── gepa_runner.py               # GEPA optimizer with Responses API grammar demos
│   ├── gepa.py                      # Toast→Neo4j pipeline
│   ├── gepa_optimizer.py            # GEPA optimization framework
│   └── gepa_feedback.py             # Feedback system
│
├── config/                          # Pipeline configurations (auto-generated)
├── logs/                            # Import execution logs
├── reports/                         # Import reports
│
├── .env                             # Environment configuration
├── AURA_SETUP.md                    # Complete Aura setup guide
├── MESSAGE_ORDERING.md              # SQS FIFO message ordering guide
├── SETUP_GUIDE.md                   # SQS setup guide
└── README.md                        # This file
```

---

## Quick Start

### 1. Install Dependencies

```bash
# Using UV (recommended)
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Or using pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Edit `.env` and add your credentials:

```bash
# Aura API (get from console.neo4j.io > Account Settings > API Keys)
AURA_API_CLIENT_ID=MPGDSjrdi1iYhpcFGkmua1LKkTCEMjPx
AURA_API_CLIENT_SECRET=LnaIH0C2BSUxTlXTnrBdZsR0Tbgxi6bbJTA8clk7wlZKe0TAmhmIOmaZuIO1FyYj

# Get these from console.neo4j.io
AURA_ORGANIZATION_ID=your-org-id
AURA_PROJECT_ID=your-project-id

# AWS (for SQS)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-2

# SQS Queue URLs
QUEUE_URL=https://sqs.us-east-2.amazonaws.com/...
DLQ_URL=https://sqs.us-east-2.amazonaws.com/...
```

### 3. Test Aura Setup

```bash
python scripts/test_aura_setup.py
```

**Expected output:**
```
✓ Environment Variables: PASSED
✓ Aura CLI: PASSED
✓ Health Check: PASSED
✓ Import API Authentication: PASSED
🎉 All tests passed!
```

**See full setup guide**: [AURA_SETUP.md](AURA_SETUP.md)

---

## Features

### 1. Aura Import API Integration ✅

Programmatic data loading from cloud data warehouses:

```python
from src.aura_manager import AuraManager

manager = AuraManager()
manager.setup_import_client()

# Trigger import job
job = manager.create_import_job(
    import_model_id="your-model-id",
    db_id="705c1e42"
)

# Wait for completion
from src.aura_import_client import print_job_progress
final_job = manager.wait_for_import_completion(
    job.id,
    callback=print_job_progress
)
```

**Features**:
- OAuth 2.0 authentication with token caching
- Idempotent imports (safe to re-run)
- Progress monitoring with callbacks
- Multiple data sources: Snowflake, BigQuery, S3

### 2. Automated Data Pipelines ✅

**Hourly Incremental Sync**:
```bash
# Configure pipeline
python scripts/setup_incremental_pipeline.py \
  --import-model-id fc371c86-... \
  --instance-id 705c1e42 \
  --schedule "0 * * * *"

# Test run
python scripts/run_import_pipeline.py \
  --pipeline-name snowflake_incremental_sync \
  --dry-run

# Schedule with cron
crontab -e
# Add: 0 * * * * cd /path/to/lab_sqs && python scripts/run_import_pipeline.py ...
```

**Historical Onboarding**:
```bash
python scripts/historical_import.py \
  --import-model-id your-historical-model-id \
  --instance-id 705c1e42 \
  --verify \
  --create-snapshot
```

### 3. GPT-5 Responses API with Cypher Grammar ✅

Context-Free Grammar for constrained Cypher generation:

```python
# From lab5_mlflow/gepa_runner.py
cypher_grammar = textwrap.dedent(r"""
    start: match_clause (SP where_clause)? SP return_clause
    match_clause: "MATCH" SP pattern
    pattern: node (SP? relationship SP? node)*
    return_clause: "RETURN" SP return_items
""")

tools = [{
    "type": "custom",
    "name": "cypher_grammar",
    "format": {"type": "grammar", "syntax": "lark", "definition": cypher_grammar}
}]

resp = await llm.create_completion(
    messages=[{"role": "user", "content": "Find restaurants with orders over $500"}],
    tools=tools
)
```

**Features**:
- Constrained Cypher generation (MATCH..RETURN patterns)
- MSSQL grammar example
- Verbosity control (low/medium/high)
- Minimal reasoning mode

### 4. SQS Message Queue ✅

**Start Consumer**:
```bash
python src/consumer.py
```

**Send Messages**:
```bash
# Send 1000 messages
python src/writer.py --n 1000

# Send custom message
python src/msg_writer.py --msg "Hello SQS"
```

**Features**:
- FIFO ordering with message groups
- Dead letter queue for failed messages
- Long polling for efficiency

---

## Available Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `test_aura_setup.py` | Test all Aura components | `python scripts/test_aura_setup.py` |
| `setup_incremental_pipeline.py` | Configure automated pipelines | `--import-model-id ID --schedule "0 * * * *"` |
| `run_import_pipeline.py` | Execute pipelines | `--pipeline-name NAME [--dry-run]` |
| `historical_import.py` | One-time bulk import | `--import-model-id ID --verify` |
| `check_import_status.py` | Monitor import jobs | `--job-id ID [--watch]` |

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│              Application Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ GEPA Runner  │  │ Incremental  │  │ Historical  │ │
│  │ (GPT-5 CFG)  │  │ Pipelines    │  │ Onboarding  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
└─────────┼──────────────────┼──────────────────┼────────┘
          │                  │                  │
    ┌─────┴────────┬─────────┴──────────────────┘
    │              │
    │   ┌──────────▼───────────────┐
    │   │    Aura Manager          │
    │   │  - CLI wrapper           │
    │   │  - Import API client     │
    │   └──────────┬───────────────┘
    │              │
    │   ┌──────────▼───────────────┐
    │   │  Aura Import API v2beta1 │
    │   └──────────┬───────────────┘
    │              │
    │   ┌──────────▼──────────┐
    │   │   Neo4j Aura        │
    │   │  3 Instances:       │
    │   │  - Melting Pot KG   │
    │   │  - Proper KG        │
    │   │  - Tray KG          │
    │   └─────────────────────┘
    │              ▲
    │              │
    │   ┌──────────┴──────────┐
    │   │   Data Sources      │
    │   │  - Snowflake        │
    │   │  - BigQuery         │
    │   │  - S3               │
    │   └─────────────────────┘
    │
    └── AWS SQS (async job processing)
```

---

## Documentation

- **[AURA_SETUP.md](AURA_SETUP.md)** - Complete Aura integration setup guide
- **[MESSAGE_ORDERING.md](MESSAGE_ORDERING.md)** - SQS FIFO message ordering
- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** - SQS queue setup

---

## Integration with lab5_mlflow

This project shares components with the parent `lab5_mlflow` project:

**Shared Files**:
- `src/aura_import_client.py` - Aura Import API client
- `src/multi_neo4j_connector.py` - Multi-instance Neo4j connector

**Related Projects**:
- **GEPA Optimizer** - Genetic-Pareto prompt optimization
- **MLFlow Integration** - Model tracking and serving
- **Federated GraphQL** - Unified data access layer

**See**: `/lab5_mlflow/DEPLOYMENT_SUMMARY.md`

---

## Workflow Examples

### Daily Automated Import

```bash
# 1. Create import model in Aura Console for daily data
# 2. Set up pipeline
python scripts/setup_incremental_pipeline.py \
  --import-model-id <model-id> \
  --instance-id 705c1e42 \
  --schedule "0 2 * * *"  # 2 AM daily

# 3. Add to crontab
crontab -e
```

### Historical Onboarding

```bash
# 1. Create import model for all historical data
# 2. Run one-time import
python scripts/historical_import.py \
  --import-model-id <historical-model-id> \
  --instance-id 705c1e42 \
  --knowledge-graph melting-pot \
  --verify \
  --create-snapshot

# 3. Verify in Neo4j Browser
# MATCH (o:Order) RETURN count(o)
```

### Monitoring Imports

```bash
# Check specific job
python scripts/check_import_status.py --job-id <job-id> --progress

# Watch job until completion
python scripts/check_import_status.py --job-id <job-id> --watch

# List all configured pipelines
python scripts/run_import_pipeline.py --list
```

---

## Troubleshooting

### "Environment variables not set"

Check all 4 Aura API variables in `.env`:
- `AURA_API_CLIENT_ID`
- `AURA_API_CLIENT_SECRET`
- `AURA_ORGANIZATION_ID`
- `AURA_PROJECT_ID`

Get Organization and Project IDs from [console.neo4j.io](https://console.neo4j.io)

### "Import job failed: Schema validation error"

1. Verify table names in import model match Snowflake schema
2. Refresh data source if tables changed
3. Test model with sample data in Aura Console

### "Duplicate nodes created"

1. Go to import model settings in Aura Console
2. Add unique constraints on ID fields (e.g., `guid`)
3. Re-run import (duplicates will be merged)

**See full guide**: [AURA_SETUP.md#troubleshooting](AURA_SETUP.md#troubleshooting)

---

## Next Steps

### Immediate

1. ✅ Complete `.env` configuration (add Organization ID, Project ID)
2. ✅ Run `python scripts/test_aura_setup.py`
3. ✅ Create first import model in Aura Console
4. ✅ Test import job trigger

### Short Term

5. Set up incremental hourly pipeline for restaurant orders
6. Run historical onboarding for existing data
7. Verify data in Neo4j Browser
8. Monitor first scheduled import

### Medium Term

9. Integrate with Airflow for orchestration
10. Add monitoring and alerting
11. Implement GEPA optimization for Cypher generation
12. Set up GraphQL federation

---

## Resources

- [Neo4j Aura Console](https://console.neo4j.io)
- [Aura Import API Docs](https://neo4j.com/docs/aura/platform/api/specification/)
- [Aura CLI Docs](https://neo4j.com/labs/aura-cli/)
- [Import Service Guide](https://neo4j.com/docs/aura/import/quick-start/)
- [GPT-5 Responses API](https://platform.openai.com/docs/)

---

**Questions?** Start with `python scripts/test_aura_setup.py` to verify your setup!
