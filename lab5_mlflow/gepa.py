"""GEPA pipeline primitives for Toast -> Neo4j processing.

This module provides lightweight, safe defaults suitable for local smoke tests.
Replace the placeholder extraction and mapping logic with your LLM-backed
implementations when ready.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
import hashlib
import logging

logger = logging.getLogger("gepa.pipeline")

try:
    from neo4j import AsyncGraphDatabase
    _HAS_NEO4J = True
except Exception:
    AsyncGraphDatabase = None
    _HAS_NEO4J = False


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
    """Simplified Toast -> Neo4j pipeline.

    The pipeline contains six modules by default. Module implementations
    here are placeholders for smoke testing and should be extended.
    """

    def __init__(self, neo4j_uri: Optional[str] = None, neo4j_auth: Optional[Tuple[str, str]] = None, database: Optional[str] = None):
        self.driver = None
        self.database = database
        if neo4j_uri and _HAS_NEO4J:
            try:
                self.driver = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
            except Exception:
                logger.exception("Failed to create Neo4j driver; continuing with driver=None")

        self.modules: Dict[str, ToastModule] = {}
        self.module_sequence: List[str] = []
        self._init_default_modules()

    def _init_default_modules(self):
        self.modules = {
            'schema_discovery': ToastModule(
                name='schema_discovery',
                prompt='Identify entity types and relationship templates from a raw Toast JSON record.',
                input_schema={'raw_json': 'object'},
                output_schema={'entities': 'array', 'relationships': 'array'},
            ),
            'entity_extraction': ToastModule(
                name='entity_extraction',
                prompt='Extract nodes and properties, include GUIDs and timestamps, deduplicate on GUID.',
                input_schema={'toast_data': 'object'},
                output_schema={'nodes': 'array'},
            ),
            'relationship_mapping': ToastModule(
                name='relationship_mapping',
                prompt='Map nodes to relationships using canonical types such as IS_PART_OF_ORDER_HEADER.',
                input_schema={'entities': 'array'},
                output_schema={'relationships': 'array'},
            ),
            'temporal_enrichment': ToastModule(
                name='temporal_enrichment',
                prompt='Add temporal nodes/relations for dates, shifts, hours.',
                input_schema={'nodes': 'array', 'timestamp_fields': 'array'},
                output_schema={'temporal_nodes': 'array', 'temporal_relationships': 'array'},
            ),
            'alert_generation': ToastModule(
                name='alert_generation',
                prompt='Detect fraud/anomaly patterns and return structured alerts.',
                input_schema={'aggregated_data': 'object'},
                output_schema={'alerts': 'array'},
            ),
            'cypher_generation': ToastModule(
                name='cypher_generation',
                prompt='Produce efficient Cypher for batch ingestion; prefer UNWIND.',
                input_schema={'nodes': 'array', 'relationships': 'array'},
                output_schema={'cypher_queries': 'array'},
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
    # ---------------------------
    async def _discover_schema(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        raw = input_data.get('raw_json') or input_data.get('toast_data') or {}
        entities = []
        relationships = []
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, dict):
                    entities.append({'label': k, 'example': str(list(v.keys())[:10])})
        return {'entities': entities, 'relationships': relationships}

    async def _extract_entities(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        toast = input_data.get('toast_data', input_data.get('raw_json', {})) or {}
        nodes = []
        # Very small heuristic: pick order and nested selections
        order = toast.get('order') or toast.get('orderHeader') or {}
        if isinstance(order, dict) and order:
            nodes.append({'label': 'Order', 'guid': order.get('guid') or order.get('id'), 'props': order})
            for sel in order.get('selections', []) or []:
                nodes.append({'label': 'ProperHotelToastOrderLineItem', 'guid': sel.get('guid') or sel.get('id'), 'props': sel})
            emp = order.get('employee') or order.get('server')
            if isinstance(emp, dict):
                nodes.append({'label': 'ProperHotelToastEmployee', 'guid': emp.get('guid') or emp.get('entityId') or emp.get('id'), 'props': emp})
        return {'nodes': nodes, 'nodes_created': len(nodes)}

    async def _map_relationships(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        nodes = input_data.get('nodes', [])
        rels = []
        orders = {n.get('guid'): n for n in nodes if n.get('label') == 'Order' and n.get('guid')}
        for n in nodes:
            if n.get('label') == 'ProperHotelToastOrderLineItem':
                order_guid = n.get('props', {}).get('orderGuid') or n.get('props', {}).get('order_guid')
                if order_guid and order_guid in orders:
                    rels.append({'type': 'IS_PART_OF_ORDER_HEADER', 'from': n.get('guid'), 'to': order_guid})
        return {'relationships': rels, 'relationships_created': len(rels)}

    async def _enrich_temporal(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {'temporal_nodes': [], 'temporal_relationships': []}

    async def _generate_alerts(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {'alerts': []}

    async def _generate_cypher(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        nodes = input_data.get('nodes', [])
        rels = input_data.get('relationships', [])
        queries = []
        if nodes:
            queries.append("UNWIND $batch AS row MERGE (n:Node {guid: row.guid}) SET n += row.props")
        if rels:
            queries.append("UNWIND $rels AS r MATCH (a {guid: r.from}), (b {guid: r.to}) MERGE (a)-[x:REL]->(b)")
        return {'cypher_queries': queries}
