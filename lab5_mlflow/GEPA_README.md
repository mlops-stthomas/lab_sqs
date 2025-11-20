GEPA (Genetic-Pareto) Prompt Optimizer
=====================================

This directory contains a lightweight, production-oriented scaffold for GEPA
(Genetic-Pareto) Prompt Optimizer tailored for a Toast POS → Neo4j pipeline.

Files
-----
- `gepa.py` — Pipeline primitives: `ToastModule`, `ExecutionTrace`, `ToastNeo4jPipeline`.
- `gepa_feedback.py` — Domain-specific feedback functions for Toast → Neo4j.
- `gepa_optimizer.py` — GEPA optimizer loop (candidate pool, selection, prompt mutation).
- `gepa_runner.py` — Simple runner to run small optimization jobs using the example data.
- `config.example.yaml` — Example configuration for local runs.
- `examples/` — Tiny training/validation examples for smoke testing.
- `test_smoke.py` — Quick smoke test to validate the scaffold.

Quick start (local smoke run)
----------------------------
1. Create a Python virtualenv and install dependencies from the repo `requirements.txt`.
2. Set minimal env vars (if you plan to use OpenAI or Neo4j):

```bash
export OPENAI_API_KEY="..."      # optional; GEPA will fall back to a heuristic
export NEO4J_PASSWORD="..."      # optional; EXPLAIN-based Cypher validation is safe
```

3. Run the runner (this uses the tiny example dataset and a low budget):

```bash
python3 lab5_mlflow/gepa_runner.py --config lab5_mlflow/config.example.yaml
```

Notes
-----
- The scaffold intentionally keeps LLM usage optional; if no LLM client is configured
  GEPA falls back to a deterministic/simple prompt mutation stub so you can smoke-test
  the optimization loop without cloud calls.
- Do not run generated Cypher against production databases. Use staging and `EXPLAIN`.

Extending
---------
- Replace placeholder extraction/mapping logic in `gepa.py` with LLM-backed or
  deterministic parsers aligned to your Toast JSON schema.
- Replace `LLMAdapter` in `gepa_optimizer.py` with an enterprise LLM client that
  supports async calls for best throughput.
