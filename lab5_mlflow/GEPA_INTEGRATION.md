# GEPA-optimized GraphRAG agent for restaurant operations

## Overview

This document describes the integration of:
- **GEPA** (Genetic-Pareto prompt optimization)
- **Neo4j Aura Agent** (GraphRAG platform)
- **MLFlow** (ML model tracking)
- **Snowflake** (data warehouse)
- **Existing restaurant operations graph** (Toast POS, OpenTable, etc.)

## System architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     GEPA-Optimized Data Agent System                         │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                  Agent Module Pipeline (Φ)                            │   │
│  │                                                                        │   │
│  │  M1: Task Classifier     M2: Schema Router    M3: Query Generator    │   │
│  │   ┌────────────┐          ┌──────────────┐     ┌────────────────┐    │   │
│  │   │ Input:     │          │ Input:       │     │ Input:         │    │   │
│  │   │ user_query │─────────▶│ - query      │────▶│ - task_type    │    │   │
│  │   │            │          │ - task_type  │     │ - schema       │    │   │
│  │   │ Output:    │          │              │     │ - entities     │    │   │
│  │   │ - task_    │          │ Output:      │     │                │    │   │
│  │   │   type     │          │ - schema     │     │ Output:        │    │   │
│  │   │ - domain   │          │ - entities   │     │ - SQL/Cypher   │    │   │
│  │   │ - route    │          │ - context    │     │ - params       │    │   │
│  │   └────────────┘          └──────────────┘     └────────────────┘    │   │
│  │                                                          │             │   │
│  │                                                          ▼             │   │
│  │  M4: Execution Planner             M5: Answer Synthesizer             │   │
│  │   ┌────────────────┐                ┌──────────────────┐              │   │
│  │   │ Input:         │                │ Input:           │              │   │
│  │   │ - query        │───────────────▶│ - raw_records    │              │   │
│  │   │ - params       │                │ - metadata       │              │   │
│  │   │                │                │ - user_query     │              │   │
│  │   │ Output:        │                │                  │              │   │
│  │   │ - raw_records  │                │ Output:          │              │   │
│  │   │ - metadata     │                │ - final_answer   │              │   │
│  │   │ - latency      │                │ - explanation    │              │   │
│  │   └────────────────┘                │ - confidence     │              │   │
│  │                                      └──────────────────┘              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │               GEPA Optimization Loop (Offline)                        │   │
│  │                                                                        │   │
│  │  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐           │   │
│  │  │ Eval on     │───▶│ Select       │───▶│ Mutation via   │           │   │
│  │  │ D_pareto    │    │ Candidate &  │    │ LLM Reflection │           │   │
│  │  │             │    │ Module       │    │                │           │   │
│  │  │ Score: μ    │    │              │    │ Meta-prompt    │           │   │
│  │  │ Feedback:μf │    │ Pareto-based │    │ on examples    │           │   │
│  │  └─────────────┘    └──────────────┘    └────────────────┘           │   │
│  │         ▲                                         │                   │   │
│  │         └─────────────────────────────────────────┘                   │   │
│  │                     New prompt candidate                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     Data & Execution Layer                            │   │
│  │                                                                        │   │
│  │  ┌─────────────────┐  ┌────────────────┐  ┌─────────────────┐        │   │
│  │  │ Snowflake       │  │ Neo4j Graph    │  │ MLFlow Registry │        │   │
│  │  │                 │  │                │  │                 │        │   │
│  │  │ - Orders        │  │ - Restaurants  │  │ - Models        │        │   │
│  │  │ - Revenue       │  │ - Employees    │  │ - Versions      │        │   │
│  │  │ - Labor         │  │ - Checks       │  │ - Lineage       │        │   │
│  │  │ - Inventory     │  │ - Payments     │  │ - Predictions   │        │   │
│  │  │ - Aggregates    │  │ - Reservations │  │                 │        │   │
│  │  │                 │  │ - ML Lineage   │  │                 │        │   │
│  │  └─────────────────┘  └────────────────┘  └─────────────────┘        │   │
│  │         ▲                     ▲                     ▲                  │   │
│  │         └─────────────────────┴─────────────────────┘                  │   │
│  │                  M4 routes to appropriate engine                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Neo4j Aura Agent Integration                       │   │
│  │                                                                        │   │
│  │  Tools Available:                                                     │   │
│  │  1. Cypher Templates (predefined queries)                            │   │
│  │  2. Vector Similarity (semantic search on embeddings)                │   │
│  │  3. Text2Cypher (dynamic query generation)                           │   │
│  │                                                                        │   │
│  │  Agent Endpoint: https://api.neo4j.io/v2beta1/.../invoke             │   │
│  │  MCP Server: Can expose via Model Context Protocol                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Module definitions for restaurant data agent

### M1: Task classifier & router

**Input**: Natural language user query

**Output**:
```json
{
  "task_type": "time_series | metric_lookup | comparison | ranking | root_cause | forecast",
  "target_domain": "sales | labor | guest | events | inventory | operations",
  "data_sources": ["SNOWFLAKE", "NEO4J", "MLFLOW"]
}
```

**Examples**:
- "Show me daily revenue for Tampa location last week" → `task_type: time_series`, `domain: sales`, `sources: [SNOWFLAKE]`
- "Why did labor costs spike on Friday?" → `task_type: root_cause`, `domain: labor`, `sources: [SNOWFLAKE, NEO4J]`
- "Find similar high-performing servers" → `task_type: comparison`, `domain: labor`, `sources: [NEO4J]`

### M2: Schema grounding & entity binding

**Input**: User query + M1 output

**Output**:
```json
{
  "schema_nodes": ["UnifiedOrder", "UnifiedLocation", "Employee", "Check"],
  "entity_bindings": {
    "location_guid": "...",
    "business_date": "2025-01-15"
  },
  "context_hints": {
    "date_range": ["2025-01-08", "2025-01-15"],
    "aggregation": "daily"
  }
}
```

**Unified entities** (always prefer these):
- `UnifiedLocation` (restaurants/hotels)
- `UnifiedOrder` (all POS orders)
- `UnifiedEmployee` (staff across locations)
- `UnifiedCheck` (guest checks)
- `UnifiedMenuItem` (menu items)
- `UnifiedDaySummary` (daily aggregates)

### M3: Query generator

**Input**: M1 + M2 outputs

**Output**:
```json
{
  "query_type": "SQL",
  "query_text": "SELECT business_date, SUM(net_sales) as daily_revenue FROM VW_UNIFIED_ORDER WHERE location_guid = $location_guid AND business_date BETWEEN $start_date AND $end_date GROUP BY business_date ORDER BY business_date",
  "params": {
    "location_guid": "...",
    "start_date": "2025-01-08",
    "end_date": "2025-01-15"
  }
}
```

**Rules**:
- Use **only** Unified* views from `schema_nodes`
- Always parameterize filters (never hardcode GUIDs/dates)
- SQL for aggregations, Cypher for graph patterns
- Single executable statement

### M4: Execution planner

**Input**: Query + params from M3

**Output**:
```json
{
  "raw_records": [...],
  "execution_metadata": {
    "latency_ms": 234,
    "row_count": 7,
    "tool_calls": ["snowflake_query"]
  }
}
```

**Execution routing**:
- `query_type: SQL` → Snowflake
- `query_type: CYPHER` → Neo4j
- Timeout threshold: 5000ms

### M5: Answer synthesizer

**Input**: Raw records + metadata + user query

**Output**:
```json
{
  "final_answer": "Daily revenue for Tampa ranged from $12,450 to $18,230 last week, with the highest sales on Friday ($18,230).",
  "explanation": "Analyzed 7 days of sales data from Snowflake VW_UNIFIED_ORDER for location Tampa (guid: ...). Peak occurred on Friday 1/12.",
  "confidence": 0.95
}
```

## GEPA scoring metric μ

For each evaluation example `e`:

```
μ(e, Φ) = 0.5 * μ_ans + 0.2 * μ_qv + 0.2 * μ_schema + 0.1 * μ_cost
```

Where:
- **μ_ans**: Answer correctness (0-1)
  - 1.0 = exact match or within tolerance
  - 0.5 = partially correct
  - 0 = wrong
- **μ_qv**: Query validity (0-1)
  - 1.0 = parses, executes, respects schema
  - 0.5 = needs trivial fix
  - 0 = fails or forbidden tables
- **μ_schema**: Schema alignment (0-1)
  - 1.0 = uses only Unified* entities
  - 0.5 = uses raw tables where Unified exists
  - 0 = wrong domain
- **μ_cost**: Efficiency (0-1)
  - Start at 1.0, penalize wasteful queries

## Example GEPA feedback for M3 (query generator)

```json
{
  "module": "M3",
  "score": 0.4,
  "feedback_text": "Query used RAW_TOAST_ORDERS instead of VW_UNIFIED_ORDER. Always prefer Unified views. Also missing business_date filter—gold query includes: business_date BETWEEN $start AND $end.",
  "traces": {
    "input": {
      "task_type": "time_series",
      "schema_nodes": ["UnifiedOrder"],
      "entity_bindings": {"location_guid": "abc123"}
    },
    "output": {
      "query_text": "SELECT * FROM RAW_TOAST_ORDERS WHERE ...",
      "error": "Used raw table, missing date filter"
    }
  }
}
```

## Neo4j Aura Agent tools for restaurant data

### Tool 1: Get restaurant performance (Cypher template)

```cypher
MATCH (loc:Restaurant {guid: $location_guid})<-[:PLACED_AT_RESTAURANT]-(order:Order)
WHERE order.business_date >= date($start_date)
  AND order.business_date <= date($end_date)
RETURN
  loc.name as restaurant_name,
  order.business_date as date,
  count(order) as order_count,
  sum(order.net_sales) as daily_revenue
ORDER BY order.business_date
```

**Parameters**:
- `location_guid` (string)
- `start_date` (string, ISO format)
- `end_date` (string, ISO format)

### Tool 2: Find similar employees by performance (Vector similarity)

Uses embeddings of employee performance profiles to find similar high-performing staff.

**Index**: `employee_performance_embedding`
**Top K**: 5

### Tool 3: Root cause analysis (Text2Cypher)

For complex "why" questions that require dynamic graph traversal.

Example: "Why did labor costs spike at Tampa on Friday?"

The agent generates Cypher to:
1. Find the spike event
2. Traverse to related employees, shifts, events
3. Identify anomalies (more staff scheduled, special event, etc.)

## MLFlow + Neo4j lineage integration

When training demand forecasting models:

```python
from src.neo4j_mlops_connector import Neo4jMLOpsConnector

connector = Neo4jMLOpsConnector()
connector.log_ml_training_run(
    model_name="demand-predictor",
    version="2",
    experiment_id="forecast-exp-001",
    run_id=mlflow_run_id,
    parameters={"model_type": "XGBoost", "max_depth": 6},
    metrics={"rmse": 145.2, "mae": 98.3},
    dataset_info={
        "name": "toast_orders_last_90_days",
        "source": "Snowflake",
        "row_count": 304380,
        "features": ["hour", "day_of_week", "weather", "events", "employee_count"]
    }
)
```

This creates:
```
(MLDataset) -[:USED_IN_TRAINING]-> (MLTrainingRun) -[:PRODUCED]->
(MLModelVersion {version: "2"}) -[:VERSION_OF]-> (MLModel {name: "demand-predictor"})
```

## Connecting predictions to operational data

When the model makes predictions:

```python
connector.log_prediction_to_order(
    model_name="demand-predictor",
    version="2",
    order_guid="toast-order-12345",
    prediction="high_demand",
    confidence=0.87,
    features={"hour": 19, "day_of_week": "Friday", "event": "Concert"}
)
```

This links:
```
(MLModelVersion) -[:PREDICTED]-> (MLPrediction) -[:FOR_ORDER]-> (Order)
```

Now you can query:
```cypher
// Find all orders predicted as high-demand that actually underperformed
MATCH (pred:MLPrediction {prediction_value: "high_demand"})-[:FOR_ORDER]->(o:Order)
WHERE o.net_sales < 100
RETURN count(o) as false_positives
```

## GEPA optimization workflow

1. **Create evaluation dataset** `D_pareto` with 50-100 representative questions
2. **Define baseline prompts** for M1-M5
3. **Run GEPA loop** (100-200 iterations):
   - Select candidate system Φ_k
   - Select module j (round-robin or weighted by score)
   - Sample minibatch from `D_feedback`
   - Collect μ_f feedback
   - Generate reflection prompt
   - LLM mutates prompt for module j
   - Local validation on minibatch
   - If improved, add to candidate pool
   - Re-score on D_pareto
4. **Deploy best candidate** from Pareto frontier

## Implementation roadmap

### Phase 1: Basic agent (Week 1)
- [ ] Set up Neo4j Aura Agent with restaurant graph
- [ ] Create 3-5 Cypher template tools
- [ ] Add vector similarity tool for employee/menu search
- [ ] Test basic queries in Aura console

### Phase 2: GEPA framework (Week 2-3)
- [ ] Implement M1-M5 modules
- [ ] Create evaluation dataset (50 examples)
- [ ] Build scoring function μ
- [ ] Implement feedback function μ_f
- [ ] Build GEPA optimization loop

### Phase 3: ML integration (Week 3-4)
- [ ] Connect Neo4j MLOps connector
- [ ] Train demand forecasting model
- [ ] Log lineage to Neo4j
- [ ] Link predictions to operational data
- [ ] Build ML-enhanced agent tools

### Phase 4: Production deployment (Week 4-5)
- [ ] Deploy optimized agent as Aura API endpoint
- [ ] Expose as MCP server for Claude Desktop
- [ ] Add monitoring and logging
- [ ] Create dashboards for agent performance
- [ ] Document for team handoff

## Example end-to-end flow

**User**: "Why did our Tampa location underperform last Friday compared to the previous Friday?"

**M1** (Task Classifier):
```json
{
  "task_type": "comparison",
  "target_domain": "sales",
  "data_sources": ["SNOWFLAKE", "NEO4J"]
}
```

**M2** (Schema Router):
```json
{
  "schema_nodes": ["UnifiedOrder", "UnifiedLocation", "UnifiedDaySummary"],
  "entity_bindings": {"location_name": "Tampa"},
  "context_hints": {
    "comparison_dates": ["2025-01-05", "2025-01-12"]
  }
}
```

**M3** (Query Generator):
```json
{
  "query_type": "SQL",
  "query_text": "SELECT business_date, SUM(net_sales) as revenue, COUNT(*) as order_count FROM VW_UNIFIED_ORDER WHERE location_name = $location AND business_date IN ($date1, $date2) GROUP BY business_date",
  "params": {"location": "Tampa", "date1": "2025-01-05", "date2": "2025-01-12"}
}
```

**M4** (Execution):
```json
{
  "raw_records": [
    {"business_date": "2025-01-05", "revenue": 18450, "order_count": 145},
    {"business_date": "2025-01-12", "revenue": 12230, "order_count": 98}
  ],
  "execution_metadata": {"latency_ms": 187, "row_count": 2}
}
```

**M5** (Synthesizer):
```json
{
  "final_answer": "Tampa's revenue dropped 34% from $18,450 to $12,230 between the two Fridays, with 47 fewer orders (145 → 98). This suggests either lower foot traffic or operational issues.",
  "explanation": "Compared business_date 1/5 vs 1/12 using VW_UNIFIED_ORDER. Significant decline in both metrics.",
  "confidence": 0.92
}
```

## Next steps

1. Review Neo4j Aura Agent tutorials
2. Set up GEPA evaluation framework
3. Create initial prompt templates for M1-M5
4. Build evaluation dataset from real restaurant questions
5. Begin GEPA optimization iterations
