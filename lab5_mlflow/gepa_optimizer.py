"""GEPA optimizer implementation (skeleton + working loop).

This module implements the Genetic-Pareto loop with a simple LLM adapter
that falls back to a deterministic prompt mutation when no LLM is available.
"""
import asyncio
import json
import logging
from copy import deepcopy
from typing import List, Dict, Any, Optional

import numpy as np

from .gepa import ToastNeo4jPipeline, ToastModule

logger = logging.getLogger("gepa.optimizer")


class LLMAdapter:
    """Adapter that prefers OpenAI Responses API (client.responses.create) and
    falls back to legacy ChatCompletion or a deterministic stub.

    This adapter accepts `messages` (list of dicts like chat messages) and
    converts them into a single text `input` for the Responses API.
    """

    def __init__(self, client: Any = None, model_name: Optional[str] = None):
        self.client = client
        self.model_name = model_name

    def _messages_to_text(self, messages: List[Dict[str, str]]) -> str:
        parts = []
        for m in messages:
            role = m.get('role', 'user')
            content = m.get('content', '')
            parts.append(f"[{role}] {content}")
        return "\n\n".join(parts)

    async def create_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
        verbosity: Optional[str] = None,
        reasoning: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """Create a completion using Responses API when available.

        Accepts extra GPT-5 params: `verbosity`, `reasoning`, and `tools` and
        forwards them to the Responses API. Falls back to ChatCompletion or
        deterministic stub when needed.
        """

        text_input = self._messages_to_text(messages)

        # No client configured -> deterministic fallback
        if self.client is None:
            class Resp:
                def __init__(self, content):
                    self.output = [{
                        'type': 'message',
                        'content': [{'type': 'output_text', 'text': content}]
                    }]
                    self.output_text = content

            fallback = "```\n# REFINED PROMPT (fallback)\n" + (text_input[:1000] + "..." if len(text_input) > 1000 else text_input) + "\n```"
            await asyncio.sleep(0)
            return Resp(fallback)

        # Prefer Responses API: client.responses.create
        try:
            responses_api = getattr(self.client, 'responses', None)
            if responses_api is not None and hasattr(responses_api, 'create'):
                # If it's async-capable (some SDKs expose sync only), try to await
                create_fn = responses_api.create
                # Build kwargs for Responses API, mapping our parameters
                kwargs = dict(model=self.model_name, input=text_input, temperature=temperature, max_output_tokens=max_tokens)
                if verbosity is not None:
                    # embed verbosity inside the `text` surface, consistent with API examples
                    kwargs['text'] = {'verbosity': verbosity}
                if reasoning is not None:
                    kwargs['reasoning'] = reasoning
                if tools is not None:
                    kwargs['tools'] = tools

                if asyncio.iscoroutinefunction(create_fn):
                    resp = await create_fn(**kwargs)
                else:
                    loop = asyncio.get_event_loop()
                    resp = await loop.run_in_executor(None, lambda: create_fn(**kwargs))
                return resp
        except Exception:
            logger.debug('Responses API call failed, falling back to ChatCompletion if available', exc_info=True)

        # Fallback to OpenAI ChatCompletion if present
        try:
            if hasattr(self.client, 'ChatCompletion') and hasattr(self.client.ChatCompletion, 'acreate'):
                resp = await self.client.ChatCompletion.acreate(model=self.model_name, messages=messages, temperature=temperature, max_tokens=max_tokens)
                return resp
            # Sync ChatCompletion
            if hasattr(self.client, 'ChatCompletion') and hasattr(self.client.ChatCompletion, 'create'):
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda: self.client.ChatCompletion.create(model=self.model_name, messages=messages, temperature=temperature, max_tokens=max_tokens))
                return resp
        except Exception:
            logger.exception('ChatCompletion fallback failed')

        # Last resort: return deterministic refinement
        class Resp2:
            def __init__(self, content):
                self.output = [{
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': content}]
                }]
                self.output_text = content

        fallback = "```\n# REFINED PROMPT (final-fallback)\n" + (text_input[:1000] + "..." if len(text_input) > 1000 else text_input) + "\n```"
        await asyncio.sleep(0)
        return Resp2(fallback)

    def extract_text_from_response(self, resp: Any) -> str:
        """Robustly extract text content from different SDK response shapes.

        Supports Responses API (`output_text`, `output` list with `content` items),
        legacy ChatCompletion (`choices` with `message.content`), and dict-shaped
        responses returned by sync SDKs.
        """
        # 1) New Responses API: easy attribute
        try:
            content = getattr(resp, 'output_text', None)
            if content:
                return content
        except Exception:
            pass

        # 2) Responses API complex `output` shape
        try:
            out = getattr(resp, 'output', None)
            if out and isinstance(out, list) and len(out) > 0:
                first = out[0]
                if isinstance(first, dict):
                    for c in first.get('content', []):
                        if isinstance(c, dict):
                            if c.get('type') == 'output_text' and 'text' in c:
                                return c.get('text')
                            if 'text' in c:
                                return c.get('text')
        except Exception:
            pass

        # 3) Legacy ChatCompletion shapes
        try:
            choices = getattr(resp, 'choices', None)
            if choices and len(choices) > 0:
                first = choices[0]
                # python-openai newer shapes: .message.content
                msg = getattr(first, 'message', None)
                if msg is not None and hasattr(msg, 'content'):
                    return msg.content
                # dict-shaped: message may be a dict or an object
                if isinstance(first, dict):
                    msg_obj = first.get('message')
                    # message could be a dict or a SimpleNamespace-like object
                    if isinstance(msg_obj, dict):
                        content = msg_obj.get('content') or msg_obj.get('text')
                        if content:
                            return content
                    else:
                        # try attribute access
                        if hasattr(msg_obj, 'content'):
                            return getattr(msg_obj, 'content')
                        # fallback to top-level text
                        txt = first.get('text')
                        if txt:
                            return txt
        except Exception:
            pass

        # 4) Fallback: try converting resp to str
        try:
            return str(resp)
        except Exception:
            return ''


class GEPAOptimizer:
    def __init__(self, pipeline: ToastNeo4jPipeline, feedback_generator: Any, llm_adapter: LLMAdapter, params: Dict[str, Any] = None):
        self.pipeline = pipeline
        self.feedback = feedback_generator
        self.llm = llm_adapter
        p = params or {}
        self.minibatch_size = p.get('minibatch_size', 3)
        self.merge_frequency = p.get('merge_frequency', 5)
        self.max_candidates = p.get('max_candidates', 20)
        self.candidate_pool: List[ToastNeo4jPipeline] = [pipeline]
        self.parent_indices: List[Optional[int]] = [None]
        self.scores_matrix = np.zeros((1, 0))
        self.iteration = 0
        self.rollouts_used = 0
        # LLM-level options forwarded to adapter (verbosity, reasoning, tools)
        self.llm_options = p.get('llm_options', {})

    async def optimize(self, train_data: List[Dict[str, Any]], val_data: List[Dict[str, Any]], budget: int = 100):
        n_val = len(val_data)
        self.scores_matrix = np.zeros((1, n_val))
        for j, ex in enumerate(val_data):
            s = await self._evaluate_example(self.candidate_pool[0], ex)
            self.scores_matrix[0, j] = s
        self.rollouts_used = n_val

        while self.rollouts_used < budget:
            self.iteration += 1
            parent_idx = self._select_pareto_candidate()
            parent = self.candidate_pool[parent_idx]
            module_idx = self.iteration % len(parent.module_sequence)
            module_name = parent.module_sequence[module_idx]

            minibatch = np.random.choice(train_data, min(self.minibatch_size, len(train_data)), replace=False)
            traces_data = []
            for ex in minibatch:
                out, traces = await parent.execute_with_traces(ex['input'])
                score = await self._evaluate_output(out, ex['expected'])
                feedback = await self.feedback.generate_feedback(out, ex['expected'], traces, module_idx)
                traces_data.append({'input': ex['input'], 'output': out, 'score': score, 'traces': traces, 'feedback': feedback})
            self.rollouts_used += len(minibatch)

            old_prompt = parent.modules[module_name].prompt
            ancestor_prompts = self._get_ancestor_prompts(parent_idx, module_name)
            new_prompt = await self._reflect_and_propose(old_prompt, traces_data, ancestor_prompts, module_name)

            new_candidate = deepcopy(parent)
            new_candidate.modules[module_name].prompt = new_prompt
            new_candidate.modules[module_name].version += 1

            scores_before = [t['score'] for t in traces_data]
            scores_after = []
            for ex in minibatch:
                out2, _ = await new_candidate.execute_with_traces(ex['input'])
                scores_after.append(await self._evaluate_output(out2, ex['expected']))

            if float(np.mean(scores_after)) > float(np.mean(scores_before)):
                # validate on full val set
                new_scores = np.zeros(n_val)
                for j, ex in enumerate(val_data):
                    new_scores[j] = await self._evaluate_example(new_candidate, ex)
                self.rollouts_used += n_val
                self.candidate_pool.append(new_candidate)
                self.parent_indices.append(parent_idx)
                self.scores_matrix = np.vstack([self.scores_matrix, new_scores])
                if len(self.candidate_pool) > self.max_candidates:
                    self._prune_candidates()

            if self.iteration % self.merge_frequency == 0:
                await self._try_merge()

        best_idx = int(np.argmax(np.mean(self.scores_matrix, axis=1)))
        return self.candidate_pool[best_idx]

    def _select_pareto_candidate(self) -> int:
        if self.scores_matrix.size == 0:
            return 0
        n_candidates, n_tasks = self.scores_matrix.shape
        task_best = []
        for j in range(n_tasks):
            best_score = np.max(self.scores_matrix[:, j])
            best_indices = list(map(int, np.where(self.scores_matrix[:, j] == best_score)[0]))
            task_best.append(set(best_indices))
        pareto_set = set()
        for best_set in task_best:
            pareto_set.update(best_set)
        non_dominated = []
        for i in pareto_set:
            dominated = False
            for j in pareto_set:
                if i == j:
                    continue
                if (np.all(self.scores_matrix[j] >= self.scores_matrix[i]) and np.any(self.scores_matrix[j] > self.scores_matrix[i])):
                    dominated = True
                    break
            if not dominated:
                non_dominated.append(i)
        if not non_dominated:
            return 0
        frequencies = [sum(1 for best_set in task_best if i in best_set) for i in non_dominated]
        probs = np.array(frequencies) / sum(frequencies) if sum(frequencies) > 0 else None
        if probs is None:
            return int(np.random.choice(non_dominated))
        return int(np.random.choice(non_dominated, p=probs))

    async def _reflect_and_propose(self, old_prompt: str, traces_data: List[Dict[str, Any]], ancestor_prompts: List[str], module_name: str) -> str:
        traces_text = []
        for i, t in enumerate(traces_data, 1):
            traces_text.append(f"Example {i}: Score={t['score']:.3f} Feedback={t['feedback'][:300]}")
        ancestor_text = "\n\n".join([p[:400] for p in ancestor_prompts])
        meta_prompt = (
            "You are optimizing a prompt for module '" + module_name + "'.\n"
            "Current prompt:\n" + old_prompt + "\n\n"
            "Recent traces:\n" + "\n".join(traces_text) + "\n\n"
            "Ancestors:\n" + ancestor_text + "\n\n"
            "Produce a single improved prompt between ``` blocks."
        )
        messages = [{"role": "user", "content": meta_prompt}]
        # Pass configured LLM options if present on the optimizer
        llm_opts = getattr(self, 'llm_options', {}) or {}
        resp = await self.llm.create_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=800,
            verbosity=llm_opts.get('verbosity'),
            reasoning=llm_opts.get('reasoning'),
            tools=llm_opts.get('tools'),
        )

        # Robust extraction of text from different SDK response shapes
        content = None
        try:
            # New Responses API: prefer resp.output_text
            content = getattr(resp, 'output_text', None)
        except Exception:
            content = None

        if not content:
            try:
                out = getattr(resp, 'output', None)
                if out and isinstance(out, list) and len(out) > 0:
                    # find first output_text or text in nested content
                    item = out[0]
                    if isinstance(item, dict):
                        for c in item.get('content', []):
                            if c.get('type') == 'output_text' and 'text' in c:
                                content = c.get('text')
                                break
                            if 'text' in c:
                                content = c.get('text')
                                break
            except Exception:
                content = None

        if not content:
            # legacy OpenAI ChatCompletion shape
            try:
                choices = getattr(resp, 'choices', None)
                if choices and len(choices) > 0:
                    # python-openai v0 clients may have .message.content
                    first = choices[0]
                    msg = getattr(first, 'message', None)
                    if msg is not None and hasattr(msg, 'content'):
                        content = msg.content
                    elif isinstance(first, dict):
                        # dict-shaped choice
                        content = first.get('message', {}).get('content') or first.get('text')
            except Exception:
                content = None

        content = content or ''
        import re
        matches = re.findall(r'```(?:\w+)?\n([\s\S]*?)```', content)
        if matches:
            return matches[0].strip()
        # fallback: append a short refinement
        return old_prompt + "\n\n# REFINE: " + (traces_data[0]['feedback'][:400] if traces_data else '')

    async def _evaluate_example(self, pipeline: ToastNeo4jPipeline, example: Dict[str, Any]) -> float:
        try:
            out, traces = await pipeline.execute_with_traces(example['input'])
            return await self._evaluate_output(out, example['expected'])
        except Exception:
            return 0.0

    async def _evaluate_output(self, output: Dict[str, Any], expected: Dict[str, Any]) -> float:
        scores = []
        if 'nodes' in output and 'expected_nodes' in expected:
            extracted = set(n.get('label') for n in output.get('nodes', []))
            expected_set = set(expected.get('expected_nodes', []))
            prec = len(extracted & expected_set) / len(extracted) if extracted else 0.0
            rec = len(extracted & expected_set) / len(expected_set) if expected_set else 0.0
            f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
            scores.append(f1)
        if 'relationships' in output and 'expected_relationships' in expected:
            created_types = set(r.get('type') for r in output.get('relationships', []))
            expected_types = set(r.get('type') for r in expected.get('expected_relationships', []))
            rel_score = len(created_types & expected_types) / len(expected_types) if expected_types else 0.0
            scores.append(rel_score)
        if 'alerts' in output and 'known_patterns' in expected:
            detected = set(a.get('pattern_type') for a in output.get('alerts', []))
            known = set(expected.get('known_patterns', []))
            alert_recall = len(detected & known) / len(known) if known else 1.0
            scores.append(alert_recall)
        if 'cypher_queries' in output:
            # Basic static validation: presence is considered valid in this scaffold
            qcnt = len(output.get('cypher_queries', []))
            scores.append(1.0 if qcnt > 0 else 0.0)
        return float(np.mean(scores)) if scores else 0.0

    def _get_ancestor_prompts(self, parent_idx: int, module_name: str) -> List[str]:
        prompts = []
        cur = parent_idx
        while cur is not None and len(prompts) < 5:
            candidate = self.candidate_pool[cur]
            prompts.append(candidate.modules[module_name].prompt)
            cur = self.parent_indices[cur]
        return prompts

    async def _try_merge(self):
        # Minimal merge: no-op in scaffold
        return None

    def _prune_candidates(self):
        avg_scores = np.mean(self.scores_matrix, axis=1)
        keep = np.argsort(avg_scores)[-self.max_candidates:]
        keep = list(map(int, keep))
        self.candidate_pool = [self.candidate_pool[i] for i in keep]
        self.parent_indices = [self.parent_indices[i] for i in keep]
        self.scores_matrix = self.scores_matrix[keep]
