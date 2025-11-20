"""Domain-specific feedback functions for Toast -> Neo4j pipeline.

These functions take pipeline outputs and a gold-standard expected dict and
return human-readable feedback strings used by GEPA's reflective step.
"""
import logging
from collections import defaultdict
from typing import Dict, Any, List

logger = logging.getLogger("gepa.feedback")


class ToastNeo4jFeedback:
    def __init__(self, neo4j_driver=None):
        self.driver = neo4j_driver

    async def generate_feedback(self, output: Dict[str, Any], gold: Dict[str, Any], traces: List[Any], module_idx: int) -> str:
        module_name = traces[module_idx].module_name if traces and len(traces) > module_idx else "unknown"
        if module_name == 'entity_extraction':
            return await self._entity_extraction_feedback(output, gold, traces)
        if module_name == 'relationship_mapping':
            return await self._relationship_mapping_feedback(output, gold, traces)
        if module_name == 'alert_generation':
            return await self._alert_generation_feedback(output, gold, traces)
        return "No specialized feedback."

    async def _entity_extraction_feedback(self, output, gold, traces) -> str:
        extracted_nodes = {n.get('label') for n in output.get('nodes', [])}
        expected = set(gold.get('expected_nodes', []))
        missing = expected - extracted_nodes
        extra = extracted_nodes - expected
        parts = []
        if missing:
            parts.append(f"MISSING ENTITIES: {sorted(list(missing))}")
            if 'ProperHotelToastOrderLineItem' in missing:
                parts.append("Root cause likely: not reading nested 'selections' array. Fix: traverse order['selections'] and payment contexts.")
        if extra:
            parts.append(f"EXTRA ENTITY LABELS: {sorted(list(extra))}")
        trace = next((t for t in traces if t.module_name == 'entity_extraction'), None)
        if trace and trace.execution_time_ms > 1000:
            parts.append(f"PERF: module took {trace.execution_time_ms:.0f}ms; consider batching.")
        return "\n\n".join(parts) or "OK"

    async def _relationship_mapping_feedback(self, output, gold, traces) -> str:
        created = output.get('relationships', [])
        created_types = defaultdict(int)
        for r in created:
            created_types[r.get('type')] += 1
        expected_counts = gold.get('relationship_counts', {})
        parts = []
        for k, exp in expected_counts.items():
            got = created_types.get(k, 0)
            if got < exp * 0.9:
                parts.append(f"REL_MISSING: {k} expected {exp}, got {got}. Check join keys (order.guid).")
                if k == 'IS_PART_OF_ORDER_HEADER':
                    parts.append("Fix: ensure each line_item.orderGuid === order.guid")
        return "\n\n".join(parts) or "OK"

    async def _alert_generation_feedback(self, output, gold, traces) -> str:
        alerts = output.get('alerts', [])
        known = set(gold.get('known_patterns', []))
        detected = {a.get('pattern_type') for a in alerts}
        missed = known - detected
        parts = []
        if missed:
            parts.append(f"MISSED_PATTERNS: {sorted(list(missed))}")
            if 'rapid_refund' in missed:
                parts.append("Add rule: refund within 5 minutes of order creation; threshold >3/day")
        return "\n\n".join(parts) or "OK"
