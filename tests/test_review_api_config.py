from types import SimpleNamespace

import server
from duanxian import review_graph


CONFIG = {"baseURL": "https://api.example.com/v1", "apiKey": "test-only-key", "model": "test-model"}


def test_both_models_use_browser_config(monkeypatch):
    calls = []
    monkeypatch.setattr(review_graph, "make_llm", lambda **kw: calls.append(kw) or object())
    monkeypatch.setattr(review_graph, "ROLES", [])
    monkeypatch.setattr(review_graph, "create_review_judge", lambda model: lambda state: {})
    review_graph.build_review_graph(request_config=CONFIG)
    assert calls == [{"deep": False, "request_config": CONFIG}, {"deep": True, "request_config": CONFIG}]


def test_route_passes_config_only_to_worker(monkeypatch):
    monkeypatch.setattr(server.trade_calendar, "is_settled", lambda date: True)
    monkeypatch.setattr(server.review_store, "load", lambda date: None)
    monkeypatch.setattr(server, "_job", dict(server._job, running=False))
    calls = []
    monkeypatch.setattr(server.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: calls.append(kw)))
    req = SimpleNamespace(headers={}, query_params={})
    response = server.api_run(req, date="2026-09-04", body={"llm": CONFIG})
    assert response["running"]
    assert calls[0]["args"][2] == CONFIG
    assert CONFIG["apiKey"] not in str(response) + str(server._job)


def test_worker_redacts_key_on_failure(monkeypatch):
    monkeypatch.setattr(server, "_job", dict(server._job, job_id="test", started=None))
    monkeypatch.setattr(server.preflight, "check", lambda date: {"ok": True})
    def fail(**kwargs):
        raise RuntimeError(CONFIG["apiKey"])
    monkeypatch.setattr(server, "build_review_graph", fail)
    server._run_review("2026-09-04", "test", CONFIG)
    assert "[REDACTED]" in server._job["error"]
    assert CONFIG["apiKey"] not in server._job["error"]
