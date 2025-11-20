"""
Airflow DAG to generate a Text2Cypher evaluation set for GEPA tuning.

This DAG writes a JSONL file with NL questions, gold Cypher, and expected keys.
It does not execute Cypher; it simply materializes a curated eval set on disk
that downstream GEPA runners can consume.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator


def build_eval_set():
    """Create a small, curated Text2Cypher eval set for restaurant ops."""
    import json
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    out_dir = repo_root / "gepa"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "text2cypher_eval.jsonl"

    # Curated examples targeting the observed labels/relationships in the graph.
    examples = [
        {
            "id": "q1_orders_by_location_date",
            "nl": "How many orders were placed at restaurant 12B471AD-1505-41B2-BA27-A480E8C16D30 on 2024-09-01?",
            "cypher_gold": (
                "MATCH (r:Restaurant {restaurantGuid: '12B471AD-1505-41B2-BA27-A480E8C16D30'})"
                "-[:BELONGS_TO_RESTAURANT]-(o:Order) "
                "WHERE date(o.businessDate) = date('2024-09-01') "
                "RETURN count(o) AS order_count"
            ),
            "expected_keys": ["order_count"],
            "notes": "Covers BELONGS_TO_RESTAURANT relationship and businessDate filtering."
        },
        {
            "id": "q2_employee_void_rate",
            "nl": "Which employees voided more than 15% of their orders last week?",
            "cypher_gold": (
                "MATCH (e:Employee)-[:CREATED_BY_EMPLOYEE]->(o:Order) "
                "WHERE o.voidReason IS NOT NULL "
                "AND o.businessDate >= date() - duration('P7D') "
                "WITH e, count(o) AS voided "
                "MATCH (e)-[:CREATED_BY_EMPLOYEE]->(all:Order) "
                "WHERE all.businessDate >= date() - duration('P7D') "
                "WITH e, voided, count(all) AS total "
                "WHERE total > 0 AND toFloat(voided)/total > 0.15 "
                "RETURN e.employeeGuid AS employee_id, voided, total, toFloat(voided)/total AS void_rate "
                "ORDER BY void_rate DESC"
            ),
            "expected_keys": ["employee_id", "voided", "total", "void_rate"],
            "notes": "Targets void patterns and CREATED_BY_EMPLOYEE coverage."
        },
        {
            "id": "q3_top_modifiers",
            "nl": "Top 5 modifiers by frequency across all line items.",
            "cypher_gold": (
                "MATCH (m:Modifier)<-[:HAS_MODIFIER]-(li:ProperHotelToastOrderLineItem) "
                "RETURN m.name AS modifier, count(li) AS uses "
                "ORDER BY uses DESC LIMIT 5"
            ),
            "expected_keys": ["modifier", "uses"],
            "notes": "Covers ProperHotelToastOrderLineItem and HAS_MODIFIER."
        },
        {
            "id": "q4_payments_per_order",
            "nl": "For orders on 2024-09-01, how many payments per order and totals?",
            "cypher_gold": (
                "MATCH (o:Order)-[:HAS_PAYMENT]->(p:Payment) "
                "WHERE date(o.businessDate) = date('2024-09-01') "
                "RETURN o.guid AS order_id, count(p) AS payment_count, "
                "sum(p.amount) AS total_paid"
            ),
            "expected_keys": ["order_id", "payment_count", "total_paid"],
            "notes": "Covers HAS_PAYMENT relationships and aggregates."
        },
        {
            "id": "q5_line_items_for_order",
            "nl": "List line items for order GUID X with price and tax.",
            "cypher_gold": (
                "MATCH (o:Order {guid: $order_guid})<-[:IS_PART_OF_ORDER_HEADER]-"
                "(li:ProperHotelToastOrderLineItem) "
                "OPTIONAL MATCH (li)-[:HAS_TAX]->(t:AppliedTax) "
                "RETURN li.guid AS line_item_id, li.name AS name, li.price AS price, "
                "coalesce(sum(t.amount), 0) AS tax_total"
            ),
            "expected_keys": ["line_item_id", "name", "price", "tax_total"],
            "params": {"order_guid": "REPLACE_WITH_ORDER_GUID"},
            "notes": "Parameters example; IS_PART_OF_ORDER_HEADER and HAS_TAX."
        }
    ]

    with out_file.open("w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    print(f"✓ Wrote {len(examples)} Text2Cypher eval examples to {out_file}")


default_args = {
    "owner": "mlops",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="gepa_text2cypher_eval",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    default_args=default_args,
    description="Generate a curated Text2Cypher eval set for GEPA tuning.",
) as dag:
    generate_eval = PythonOperator(
        task_id="generate_eval_set",
        python_callable=build_eval_set,
    )

    generate_eval
