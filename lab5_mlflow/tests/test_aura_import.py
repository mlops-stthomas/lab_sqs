import json
from types import SimpleNamespace

import pytest

from lab5_mlflow import aura_import


class DummyResponse:
    def __init__(self, json_obj, status_code=200):
        self._json = json_obj
        self.status_code = status_code

    def json(self):
        return self._json
    def raise_for_status(self):
        # mimic requests.Response.raise_for_status (no-op for our dummy)
        if 400 <= self.status_code:
            raise Exception(f"HTTP {self.status_code}")


def test_create_import_job_success(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=10):
        assert 'import' in url
        return DummyResponse({'id': 'job_123', 'status': 'QUEUED'})

    # Patch only the post() function on the requests module used by aura_import
    monkeypatch.setattr(aura_import.requests, 'post', fake_post)
    token = 'tok_x'
    resp = aura_import.create_import_job(token, 'org1', 'proj1', 'model1', 'db1', api_base='https://aura.example')
    assert resp['id'] == 'job_123'


def test_get_job_status_polling(monkeypatch):
    # Simulate two calls: first returns running, second returns completed
    calls = {'n': 0}

    def fake_get(url, headers=None, timeout=10):
        calls['n'] += 1
        if calls['n'] == 1:
            return DummyResponse({'info': {'state': 'RUNNING'}})
        return DummyResponse({'info': {'state': 'COMPLETED'}})

    # Patch only the get() function
    monkeypatch.setattr(aura_import.requests, 'get', fake_get)
    token = 'tok_x'
    status1 = aura_import.get_job_status(token, 'org1', 'proj1', 'job_123', api_base='https://aura.example')
    assert status1['info']['state'] in ('RUNNING', 'COMPLETED')


def test_get_token_and_cancel(monkeypatch):
    def fake_post_token(url, data=None, timeout=10):
        return DummyResponse({'access_token': 'tok_generated'})

    def fake_post_cancel(url, headers=None, json=None, timeout=10):
        assert 'cancel' in url
        return DummyResponse({'status': 'CANCELLED'})

    # Patch requests.post to route by URL
    def _post_router(url, headers=None, json=None, data=None, timeout=10):
        if 'oauth' in url:
            return fake_post_token(url, data=data, timeout=timeout)
        return fake_post_cancel(url, headers=headers, json=json, timeout=timeout)

    monkeypatch.setattr(aura_import.requests, 'post', _post_router)

    token = aura_import.get_token('cid', 'secret', oauth_url='https://aura.example/oauth/token')
    assert token == 'tok_generated'
    resp = aura_import.cancel_job('tok_generated', 'org1', 'proj1', 'job_123', api_base='https://aura.example')
    assert resp['status'] == 'CANCELLED'
