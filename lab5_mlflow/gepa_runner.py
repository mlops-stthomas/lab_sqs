#!/usr/bin/env python3
"""Runner for GEPA optimizer (small smoke-run).

Usage: python3 lab5_mlflow/gepa_runner.py --config lab5_mlflow/config.example.yaml
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path

import yaml
import textwrap

from lab5_mlflow.gepa import ToastNeo4jPipeline
from lab5_mlflow.gepa_feedback import ToastNeo4jFeedback
from lab5_mlflow.gepa_optimizer import GEPAOptimizer, LLMAdapter

logger = logging.getLogger("gepa.runner")
logging.basicConfig(level=logging.INFO)


def load_examples(path: Path):
    with open(path, 'r') as f:
        return json.load(f)


async def main_async(config_path: Path):
    cfg = yaml.safe_load(open(config_path))
    neo4j_cfg = cfg.get('neo4j', {})
    gepa_cfg = cfg.get('gepa', {})

    examples_dir = Path(__file__).parent / 'examples'
    train = load_examples(examples_dir / 'toast_training.json')
    val = load_examples(examples_dir / 'toast_validation.json')

    neo4j_uri = neo4j_cfg.get('uri')
    neo4j_user = neo4j_cfg.get('user')
    neo4j_pass = None
    if neo4j_cfg.get('password_env'):
        import os
        neo4j_pass = os.environ.get(neo4j_cfg.get('password_env'))

    pipeline = ToastNeo4jPipeline(neo4j_uri=neo4j_uri, neo4j_auth=(neo4j_user, neo4j_pass) if neo4j_user else None, database=neo4j_cfg.get('database'))
    feedback = ToastNeo4jFeedback(pipeline.driver)

    # Try to use OpenAI if available; otherwise adapter will fallback
    llm_client = None
    try:
        import openai
        llm_client = openai
        if cfg.get('openai', {}).get('api_key_env'):
            import os
            openai.api_key = os.environ.get(cfg['openai']['api_key_env'])
    except Exception:
        logger.info('OpenAI SDK not found; using deterministic fallback adapter')

    # Attach optional verbosity/reasoning/tools config for GPT-5 Responses API
    openai_cfg = cfg.get('openai', {})
    extra_llm_opts = {
        'verbosity': openai_cfg.get('verbosity'),
        'reasoning': openai_cfg.get('reasoning'),
        'tools': openai_cfg.get('tools'),
        #
        # Example: GPT Responses API tool / grammar usage
        # Pass a simple "generate_cypher" tool schema that the LLM can call.
        #
        # To enable, add to config:
        # openai:
        #   tools:
        #     - type: "function"
        #       function:
        #         name: "generate_cypher"
        #         description: "Return a Cypher string answering the question."
        #         parameters:
        #           type: object
        #           properties:
        #             cypher:
        #               type: string
        #               description: "Cypher query to run"
        #           required: ["cypher"]
    }

    llm = LLMAdapter(client=llm_client, model_name=openai_cfg.get('model'))
    # Pass extra LLM options into optimizer params so the optimizer can use them
    gepa_params = dict(gepa_cfg)
    gepa_params['llm_options'] = extra_llm_opts
    optimizer = GEPAOptimizer(pipeline, feedback, llm, params=gepa_params)

    # Helper function to extract content from various OpenAI response formats
    def _extract_response_content(resp):
        """Extract text content from Responses API or legacy ChatCompletion formats.

        Prefer the LLM adapter's extraction helper when available, else fall back
        to the local extraction logic for compatibility.
        """
        # If adapter implements extraction helper, use it (centralized logic)
        try:
            if hasattr(llm, 'extract_text_from_response'):
                return llm.extract_text_from_response(resp)
        except Exception:
            logger.debug('llm.extract_text_from_response failed; falling back', exc_info=True)

        # Fallback: robust extraction similar to adapter
        content = getattr(resp, 'output_text', None) or ''
        if not content:
            out = getattr(resp, 'output', None)
            if out and isinstance(out, list) and len(out) > 0 and isinstance(out[0], dict):
                for c in out[0].get('content', []):
                    if c.get('type') == 'output_text' and 'text' in c:
                        content = c.get('text')
                        break

        if not content:
            # Last resort: try legacy ChatCompletion shape
            choices = getattr(resp, 'choices', None)
            if choices and len(choices) > 0:
                first = choices[0]
                msg = getattr(first, 'message', None)
                if msg is not None and hasattr(msg, 'content'):
                    content = msg.content
                elif isinstance(first, dict):
                    content = first.get('message', {}).get('content') or first.get('text', '')

        return content

    # Small Responses API grammar/tool demo (runs only when OpenAI SDK is present)
    async def _responses_grammar_demo():
        if llm_client is None:
            logger.info('OpenAI SDK not available; skipping Responses API grammar demo')
            return

        # === DEMO 1: Simple MSSQL Lark grammar ===
        mssql_grammar = textwrap.dedent(r"""
            SP: " "
            COMMA: ","
            NUMBER: /[0-9]+/
            IDENTIFIER: /[A-Za-z_][A-Za-z0-9_]*/
            start: "SELECT" SP "TOP" SP NUMBER SP select_list SP "FROM" SP table SP "WHERE" SP predicate SP SEMI
            select_list: column (COMMA SP column)*
            column: IDENTIFIER
            table: IDENTIFIER
            predicate: IDENTIFIER SP ">" SP NUMBER
            SEMI: ";"
        """)

        tools_mssql = [
            {
                "type": "custom",
                "name": "mssql_grammar",
                "description": "Return a SELECT TOP query matching a small MSSQL grammar.",
                "format": {"type": "grammar", "syntax": "lark", "definition": mssql_grammar},
            }
        ]

        messages_mssql = [{"role": "user", "content": "Generate a MSSQL query: top 5 orders by order_date where total_amount > 500; return customer_id and order_id."}]
        try:
            resp = await llm.create_completion(
                messages=messages_mssql,
                temperature=0.0,
                max_tokens=300,
                verbosity=extra_llm_opts.get('verbosity'),
                reasoning=extra_llm_opts.get('reasoning'),
                tools=tools_mssql,
            )

            content = _extract_response_content(resp)
            logger.info('=== MSSQL Grammar Demo ===\n%s', content)
        except Exception:
            logger.exception('MSSQL grammar demo failed; continuing')

        # === DEMO 2: Neo4j Cypher Lark grammar ===
        # Simplified Cypher grammar for MATCH..RETURN patterns
        cypher_grammar = textwrap.dedent(r"""
            SP: " "
            COMMA: ","
            LPAREN: "("
            RPAREN: ")"
            LBRACE: "{"
            RBRACE: "}"
            COLON: ":"
            ARROW_RIGHT: "->"
            DASH: "-"
            LBRACKET: "["
            RBRACKET: "]"

            IDENTIFIER: /[A-Za-z_][A-Za-z0-9_]*/
            STRING: /"[^"]*"/
            NUMBER: /[0-9]+(\.[0-9]+)?/

            start: match_clause (SP where_clause)? SP return_clause

            match_clause: "MATCH" SP pattern
            pattern: node (SP? relationship SP? node)*

            node: LPAREN var (COLON label)? (SP? properties)? RPAREN
            var: IDENTIFIER
            label: IDENTIFIER
            properties: LBRACE prop_list RBRACE
            prop_list: prop (COMMA SP? prop)*
            prop: IDENTIFIER COLON SP? value
            value: STRING | NUMBER | IDENTIFIER

            relationship: DASH LBRACKET var? (COLON rel_type)? RBRACKET ARROW_RIGHT
            rel_type: IDENTIFIER

            where_clause: "WHERE" SP condition
            condition: var "." IDENTIFIER SP operator SP value
            operator: ">" | "<" | "=" | ">=" | "<=" | "<>"

            return_clause: "RETURN" SP return_items
            return_items: return_item (COMMA SP? return_item)*
            return_item: var "." IDENTIFIER | var
        """)

        tools_cypher = [
            {
                "type": "custom",
                "name": "cypher_grammar",
                "description": "Generate a Neo4j Cypher query following a simplified MATCH..RETURN pattern for restaurant order data.",
                "format": {"type": "grammar", "syntax": "lark", "definition": cypher_grammar},
            }
        ]

        messages_cypher = [{
            "role": "user",
            "content": "Generate a Cypher query to find all restaurants with orders over $500, returning restaurant name and order total amount."
        }]

        try:
            resp = await llm.create_completion(
                messages=messages_cypher,
                temperature=0.0,
                max_tokens=400,
                verbosity=extra_llm_opts.get('verbosity'),
                reasoning=extra_llm_opts.get('reasoning'),
                tools=tools_cypher,
            )

            content = _extract_response_content(resp)
            logger.info('=== Cypher Grammar Demo ===\n%s', content)
        except Exception:
            logger.exception('Cypher grammar demo failed; continuing')

    # Run the demo asynchronously (non-fatal)
    try:
        await _responses_grammar_demo()
    except Exception:
        logger.exception('Responses demo failed at top level; ignoring')

    optimized = await optimizer.optimize(train, val, budget=gepa_cfg.get('budget', 20))

    out = {}
    for n, m in optimized.modules.items():
        out[n] = {'prompt': m.prompt, 'version': m.version, 'fingerprint': m.fingerprint()}

    Path('optimized_prompts.yaml').write_text(yaml.safe_dump(out))
    logger.info('Saved optimized_prompts.yaml')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=str, default='lab5_mlflow/config.example.yaml')
    args = p.parse_args()
    asyncio.run(main_async(Path(args.config)))


if __name__ == '__main__':
    main()
