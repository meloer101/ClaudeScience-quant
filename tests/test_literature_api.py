import pytest
from fastapi.testclient import TestClient

from _pdf_fixture import make_text_pdf


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("quantbench.api.run_reader.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quantbench.literature.store.LITERATURE_DIR", tmp_path / "lit")
    from quantbench.api.server import app

    return TestClient(app)


def _ingest_local(tmp_path, client, pages):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(make_text_pdf(pages))
    return client.post("/api/literature/ingest", json={"source": str(pdf)})


def test_ingest_list_and_get_paper(tmp_path, client):
    resp = _ingest_local(tmp_path, client, [["Momentum Paper", "12-1 signal."], ["Sharpe 0.9."]])
    assert resp.status_code == 200
    paper_id = resp.json()["paper_id"]
    assert resp.json()["title"] == "Momentum Paper"
    assert resp.json()["n_pages"] == 2

    listing = client.get("/api/literature").json()
    assert [p["paper_id"] for p in listing] == [paper_id]

    detail = client.get(f"/api/literature/{paper_id}").json()
    assert len(detail["pages"]) == 2
    assert "Sharpe 0.9" in detail["pages"][1]["text"]


def test_get_paper_pdf_returns_bytes(tmp_path, client):
    paper_id = _ingest_local(tmp_path, client, [["Title", "Body"]]).json()["paper_id"]
    resp = client.get(f"/api/literature/{paper_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_get_missing_paper_404(client):
    assert client.get("/api/literature/deadbeef").status_code == 404
    assert client.get("/api/literature/deadbeef/pdf").status_code == 404


def test_ingest_rejects_missing_file(client):
    resp = client.post("/api/literature/ingest", json={"source": "/nope/missing.pdf"})
    assert resp.status_code == 404


def test_ask_endpoint_grounds_on_selection(tmp_path, client, monkeypatch):
    from types import SimpleNamespace

    # Stub the LLM so no network/key is needed; capture the grounded prompt.
    captured = {}

    def fake_chat(self, messages, tools=None):
        captured["messages"] = messages
        msg = SimpleNamespace(content="It is the 12-1 momentum signal.", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr("quantbench.agent.llm.LLMClient.chat", fake_chat)

    paper_id = _ingest_local(
        tmp_path, client, [["Intro"], ["The 12-1 momentum signal skips the last month."]]
    ).json()["paper_id"]

    resp = client.post(
        f"/api/literature/{paper_id}/ask",
        json={"selection": "12-1 momentum signal", "question": "What is this?", "page": 2},
    )
    assert resp.status_code == 200
    assert "momentum" in resp.json()["answer"].lower()
    assert resp.json()["grounded_page"] == 2
    # The grounded prompt must contain the highlighted selection and page text.
    user_msg = captured["messages"][-1]["content"]
    assert "12-1 momentum signal" in user_msg
    assert "skips the last month" in user_msg


def test_ask_requires_question(tmp_path, client):
    paper_id = _ingest_local(tmp_path, client, [["a"], ["b"]]).json()["paper_id"]
    resp = client.post(f"/api/literature/{paper_id}/ask", json={"selection": "x", "question": "  "})
    assert resp.status_code == 400


def test_reproduce_endpoint_launches_run(tmp_path, client, monkeypatch):
    paper_id = _ingest_local(tmp_path, client, [["a"], ["b"]]).json()["paper_id"]

    calls = {}

    def fake_submit(self, pid, request=None, focus=None):
        calls["args"] = (pid, request, focus)
        return "run_20260704_000000_zzzz"

    monkeypatch.setattr("quantbench.api.run_manager.RunManager.submit_reproduce_paper", fake_submit)

    resp = client.post(
        f"/api/literature/{paper_id}/reproduce",
        json={"request": "reproduce on sp500", "selection": "the momentum factor", "page": 1},
    )
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run_20260704_000000_zzzz"
    assert calls["args"] == (paper_id, "reproduce on sp500", "the momentum factor")


def test_reproduce_missing_paper_404(client, monkeypatch):
    resp = client.post("/api/literature/deadbeef/reproduce", json={})
    assert resp.status_code == 404
