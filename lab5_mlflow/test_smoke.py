"""Smoke test for GEPA scaffold.

Run with: `python3 lab5_mlflow/test_smoke.py`
"""
import asyncio
from pathlib import Path

from lab5_mlflow.gepa import ToastNeo4jPipeline
from lab5_mlflow.gepa_feedback import ToastNeo4jFeedback
from lab5_mlflow.gepa_optimizer import GEPAOptimizer, LLMAdapter


async def run_smoke():
    examples_dir = Path(__file__).parent / 'examples'
    import json
    train = json.load(open(examples_dir / 'toast_training.json'))
    val = json.load(open(examples_dir / 'toast_validation.json'))

    pipeline = ToastNeo4jPipeline()
    feedback = ToastNeo4jFeedback(pipeline.driver)
    llm = LLMAdapter(client=None, model_name='gpt-4o-mini')
    opt = GEPAOptimizer(
        pipeline,
        feedback,
        llm,
        params={'minibatch_size': 1, 'merge_frequency': 2, 'max_candidates': 3, 'llm_options': {'verbosity': 'low', 'reasoning': {'effort': 'minimal'}}},
    )

    best = await opt.optimize(train, val, budget=6)
    print('Best candidate prompts:')
    for name, m in best.modules.items():
        print(f"- {name}: v{m.version} len={len(m.prompt)}")


if __name__ == '__main__':
    asyncio.run(run_smoke())
