from datetime import datetime, timedelta
import os
from airflow import DAG
from airflow.operators.python import PythonOperator

# Minimal training wrapper that sets MLFLOW_TRACKING_URI env and runs train.py
def run_training():
    import os, sys, subprocess, pathlib, shlex

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    train_py = repo_root / "src" / "train.py"

    # Environment: write runs to repo_root/mlruns, ensure src/ imports work if needed
    env = os.environ.copy()
    env.setdefault("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    env["PYTHONPATH"] = str(repo_root) + (os.pathsep + env.get("PYTHONPATH","") if env.get("PYTHONPATH") else "")

    cmd = [sys.executable, str(train_py)]
    print(f"[runner] exec: {' '.join(shlex.quote(c) for c in cmd)}")
    print(f"[runner] cwd:  {repo_root}")
    print(f"[runner] MLFLOW_TRACKING_URI={env['MLFLOW_TRACKING_URI']}")

    # Capture output so Airflow logs show the real error
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        # keep stderr visible in Airflow logs
        print(proc.stderr, end="", file=sys.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"train.py failed with exit code {proc.returncode}")
default_args = {
    "owner": "you",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="train_model",
    start_date=datetime(2024, 1, 1),
    schedule=None,  # manual only
    catchup=False,
    default_args=default_args,
    description="Train a tiny model and log to MLflow",
) as dag:
    train = PythonOperator(
        task_id="train_model",
        python_callable=run_training,
    )

    train    # lab5_mlflow/gepa.py
    import json
    import asyncio
    import hashlib
    import logging
    from dataclasses import dataclass, field
    from typing import Dict, Any, List, Tuple, Optional
    from datetime import datetime
    import numpy as np
    
    from neo4j import AsyncGraphDatabase, AsyncDriver
    
    logger = logging.getLogger("gepa")
    logger.setLevel(logging.INFO)
    
    @dataclass
    class ToastModule:
        name: str
        prompt: str
        input_schema: Dict[str, Any]
        output_schema: Dict[str, Any]
        version: int = 1
        performance_history: List[float] = field(default_factory=list)
    
        def fingerprint(self) -> str:
            content = f"{self.name}:{self.prompt}:{self.version}"
            return hashlib.md5(content.encode()).hexdigest()[:8]
    
    @dataclass
    class ExecutionTrace:
        module_name: str
        input_data: Dict[str, Any]
        output_data: Dict[str, Any]
        execution_time_ms: float
        success: bool
        error_message: Optional[str] = None
        cypher_queries: List[str] = field(default_factory=list)
        nodes_created: int = 0
        relationships_created: int = 0
        validation_errors: List[str] = field(default_factory=list)
    
    class ToastNeo4jPipeline:
        def __init__(self, neo4j_uri: str, neo4j_auth: Tuple[str, str], database: Optional[str]=None):
            self.driver: AsyncDriver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
            self.database = database
            self.modules: Dict[str, ToastModule] = {}
            self.module_sequence: List[str] = []
            self._init_default_modules()
    
        def _init_default_modules(self):
            self.modules = {
                'schema_discovery': ToastModule(
                    name='schema_discovery',
                    prompt=("Identify entity types and relationship templates from a raw Toast JSON record. "
                            "Return JSON: {'entities': [...], 'relationships': [...]}"),
                    input_schema={'raw_json': 'object'},
                    output_schema={'entities': 'array', 'relationships': 'array'}
                ),
                'entity_extraction': ToastModule(
                    name='entity_extraction',
                    prompt=("Extract node objects with labels and properties from Toast JSON. "
                            "Include toast GUIDs and timestamps. Deduplicate on GUID."),
                    input_schema={'toast_data': 'object'},
                    output_schema={'nodes': 'array'}
                ),
                'relationship_mapping': ToastModule(
                    name='relationship_mapping',
                    prompt=("Map extracted nodes to relationship objects. Use canonical relationship types "
                            "like IS_PART_OF_ORDER_HEADER, CREATED_BY_EMPLOYEE."),
                    input_schema={'entities': 'array', 'toast_data': 'object'},
                    output_schema={'relationships': 'array'}
                ),
                'temporal_enrichment': ToastModule(
                    name='temporal_enrichment',
                    prompt=("Create date/time nodes and temporal relationships for analytics."),
                    input_schema={'nodes': 'array', 'timestamp_fields': 'array'},
                    output_schema={'temporal_nodes': 'array', 'temporal_relationships': 'array'}
                ),
                'alert_generation': ToastModule(
                    name='alert_generation',
                    prompt=("From aggregated features detect fraud/anomaly patterns; return structured alerts."),
                    input_schema={'aggregated_data': 'object'},
                    output_schema={'alerts': 'array'}
                ),
                'cypher_generation': ToastModule(
                    name='cypher_generation',
                    prompt=("Produce efficient Cypher statements for batch ingestion; prefer UNWIND; include indexes."),
                    input_schema={'nodes': 'array', 'relationships': 'array'},
                    output_schema={'cypher_queries': 'array'}
                ),
            }
            self.module_sequence = [
                'schema_discovery', 'entity_extraction', 'relationship_mapping',
                'temporal_enrichment', 'alert_generation', 'cypher_generation'
            ]
    
        async def execute_with_traces(self, input_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[ExecutionTrace]]:
            traces: List[ExecutionTrace] = []
            current = input_data
            for name in self.module_sequence:
                module = self.modules[name]
                trace = await self._execute_module(module, current)
                traces.append(trace)
                if not trace.success:
                    break
                current = trace.output_data
            return current, traces
    
        async def _execute_module(self, module: ToastModule, input_data: Dict[str, Any]) -> ExecutionTrace:
            start = datetime.utcnow()
            try:
                # NOTE: placeholder implementations should be replaced with LLM or deterministic logic
                if module.name == 'schema_discovery':
                    output = await self._discover_schema(input_data)
                elif module.name == 'entity_extraction':
                    output = await self._extract_entities(input_data)
                elif module.name == 'relationship_mapping':
                    output = await self._map_relationships(input_data)
                elif module.name == 'temporal_enrichment':
                    output = await self._enrich_temporal(input_data)
                elif module.name == 'alert_generation':
                    output = await self._generate_alerts(input_data)
                elif module.name == 'cypher_generation':
                    output = await self._generate_cypher(input_data)
                else:
                    raise ValueError("Unknown module: " + module.name)
    
                elapsed = (datetime.utcnow() - start).total_seconds() * 1000.0
                return ExecutionTrace(module.name, input_data, output, elapsed, True,
                                      nodes_created=output.get('nodes_created', 0),
                                      relationships_created=output.get('relationships_created', 0),
                                      cypher_queries=output.get('cypher_queries', []))
            except Exception as e:
                logger.exception("Module failure %s", module.name)
                elapsed = (datetime.utcnow() - start).total_seconds() * 1000.0
                return ExecutionTrace(module.name, input_data, {}, elapsed, False, error_message=str(e))
    
        # ---------------------------
        # Minimal placeholder implementations
        # Replace with LLM-backed or deterministic functions that implement module.prompt
        # ---------------------------
        async def _discover_schema(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
            raw = input_data.get('raw_json') or input_data.get('toast_data') or {}
            # best-effort schema discovery: list top-level keys as entity candidates
            entities = []
            relationships = []
            if isinstance(raw, dict):
                entities = [{'label': k, 'example': str(v)[:200]} for k, v in raw.items() if isinstance(v, dict)]
            return {'entities': entities, 'relationships': relationships}
    
        async def _extract_entities(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
            toast = input_data.get('toast_data', input_data.get('raw_json', {}))
            nodes = []
            # simple heuristic extraction for example; replace with LLM extraction
            if 'order' in toast:
                o = toast['order']
                nodes.append({'label': 'Order', 'guid': o.get('guid'), 'props': o})
                for sel in o.get('selections', []):
                    nodes.append({'label': 'ProperHotelToastOrderLineItem', 'guid': sel.get('guid'), 'props': sel})
                emp = o.get('employee') or o.get('server')
                if emp:
                    nodes.append({'label': 'ProperHotelToastEmployee', 'guid': emp.get('guid') or emp.get('entityId'), 'props': emp})
            return {'nodes': nodes, 'nodes_created': len(nodes)}
    
        async def _map_relationships(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
            nodes = input_data.get('nodes', [])
            rels = []
            # basic join heuristics
            orders = {n['guid']: n for n in nodes if n['label'] == 'Order' and n.get('guid')}
            for n in nodes:
                if n['label'] == 'ProperHotelToastOrderLineItem':
                    order_guid = n['props'].get('orderGuid') or n['props'].get('order_guid')
                    if order_guid and order_guid in orders:
                        rels.append({'type': 'IS_PART_OF_ORDER_HEADER', 'from': n['guid'], 'to': order_guid})
            return {'relationships': rels, 'relationships_created': len(rels)}
    
        async def _enrich_temporal(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
            # placeholder
            return {'temporal_nodes': [], 'temporal_relationships': []}
    
        async def _generate_alerts(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
            # placeholder
            return {'alerts': []}
    
        async def _generate_cypher(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
            nodes = input_data.get('nodes', [])
            rels = input_data.get('relationships', [])
            queries = []
            # small UNWIND ingest example
            if nodes:
                queries.append("UNWIND $batch AS row MERGE (n:Node {guid: row.guid}) SET n += row.props")
            if rels:
                queries.append("UNWIND $rels AS r MATCH (a {guid: r.from}), (b {guid: r.to}) MERGE (a)-[:{type}]->(b)")
            return {'cypher_queries': queries}