import sys
import types
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so tests can import `lab5_mlflow` package
REPO_ROOT = Path(__file__).parents[1].parent.resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab5_mlflow.gepa_optimizer import LLMAdapter


def test_extract_output_text_attr():
    a = LLMAdapter()
    class Resp:
        def __init__(self, t):
            self.output_text = t

    resp = Resp('hello world')
    assert a.extract_text_from_response(resp) == 'hello world'


def test_extract_output_list_content():
    a = LLMAdapter()
    class Resp:
        def __init__(self, t):
            self.output = [{'type': 'message', 'content': [{'type': 'output_text', 'text': t}]}]

    resp = Resp('list content')
    assert a.extract_text_from_response(resp) == 'list content'


def test_extract_legacy_choices_message_content():
    a = LLMAdapter()
    class Resp:
        def __init__(self, t):
            self.choices = [{'message': types.SimpleNamespace(content=t)}]

    resp = Resp('legacy content')
    assert a.extract_text_from_response(resp) == 'legacy content'


def test_extract_dict_shaped_choice():
    a = LLMAdapter()
    resp = types.SimpleNamespace()
    # emulate dict-shaped choices returned by some SDKs
    resp.choices = [ {'message': {'content': 'dict content'}} ]
    assert a.extract_text_from_response(resp) == 'dict content'


def test_fallback_to_str():
    a = LLMAdapter()
    class Obj:
        def __str__(self):
            return 'serialized'

    o = Obj()
    assert a.extract_text_from_response(o) == 'serialized'
