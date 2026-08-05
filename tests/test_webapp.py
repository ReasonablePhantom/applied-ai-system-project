"""Tests for the Flask web UI (webapp.py).

Self-contained fixtures (not imported from test_agent_workflow.py) — tests/
has no __init__.py, and each test module in this suite already keeps its
own fixtures rather than cross-importing.
"""

import json

from llm_client import MockClient
from webapp import create_app

RETRIEVED_CHUNKS = [
    (
        "OPERATIONS.md",
        "Part 107 caps altitude at 400 feet above ground level (AGL) for "
        "small unmanned aircraft.",
    )
]

VALID_QUESTION_JSON = json.dumps(
    {
        "question": "What is the maximum altitude for a small UAS under Part 107?",
        "choices": {
            "A": "400 feet AGL",
            "B": "500 feet AGL",
            "C": "1000 feet AGL",
            "D": "There is no limit",
        },
        "correct_answer": "A",
        "explanation": (
            "Part 107 caps altitude at 400 feet above ground level (AGL) "
            "for small unmanned aircraft."
        ),
        "citation": "OPERATIONS.md",
    }
)

VALID_FEEDBACK_JSON = json.dumps(
    {
        "feedback": (
            "Correct: Part 107 caps altitude at 400 feet above ground "
            "level (AGL) for small unmanned aircraft."
        )
    }
)


class StubKnowledgeBase:
    """Deterministic stand-in for retrieval.KnowledgeBase in web tests."""

    def __init__(self, chunks):
        self.chunks = chunks

    def retrieve_by_topic(self, topic, top_k=3):
        return self.chunks


class ExplodingKnowledgeBase:
    """Simulates a genuinely buggy component raising an untyped exception,
    to prove the global Flask error handler catches what FAAAgent's own
    internal try/except (typed errors only) does not."""

    def retrieve_by_topic(self, topic, top_k=3):
        raise RuntimeError("boom")


def make_app(responses=None, knowledge_base=None):
    app = create_app(
        llm_client=MockClient(responses=responses or []),
        knowledge_base=knowledge_base or StubKnowledgeBase(RETRIEVED_CHUNKS),
    )
    return app


def test_index_page_loads():
    app = make_app()
    client = app.test_client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")
    assert b"New Question" in resp.data


def test_new_question_then_submit_answer_full_flow():
    app = make_app(responses=[VALID_QUESTION_JSON, VALID_FEEDBACK_JSON])
    client = app.test_client()

    resp = client.post("/api/new_question", json={"topic": "operations"})
    data = resp.get_json()

    assert resp.status_code == 200
    assert set(data.keys()) == {"question", "choices", "confidence_score"}
    assert set(data["choices"].keys()) == {"A", "B", "C", "D"}
    assert data["confidence_score"] == 100

    # Lowercase choice — proves both the route and FAAAgent's own
    # normalization handle it.
    resp2 = client.post("/api/submit_answer", json={"choice": "a"})
    data2 = resp2.get_json()

    assert resp2.status_code == 200
    assert data2["correct"] is True
    assert data2["correct_answer"] == "A"
    assert "400 feet" in data2["feedback"]
    assert data2["citation"] == "OPERATIONS.md"
    assert data2["score"] == "1/1 correct (100%)"

    resp3 = client.get("/api/score")
    assert resp3.get_json() == {"score": "1/1 correct (100%)", "has_active_question": False}


def test_two_browser_sessions_are_isolated():
    # Consumed in order: client_a's new_question, client_b's new_question,
    # client_a's submit_answer feedback. The MockClient queue is shared
    # across the whole app instance, same as a real GeminiClient would be.
    app = make_app(responses=[VALID_QUESTION_JSON, VALID_QUESTION_JSON, VALID_FEEDBACK_JSON])
    client_a = app.test_client()
    client_b = app.test_client()

    resp_a = client_a.post("/api/new_question", json={"topic": "operations"})
    assert resp_a.status_code == 200

    resp_b = client_b.post("/api/new_question", json={"topic": "operations"})
    assert resp_b.status_code == 200

    resp_a2 = client_a.post("/api/submit_answer", json={"choice": "A"})
    assert resp_a2.get_json()["score"] == "1/1 correct (100%)"

    score_b = client_b.get("/api/score").get_json()
    assert score_b == {"score": "0/0 correct (0%)", "has_active_question": True}

    assert len(app.agents) == 2


def test_new_question_with_no_reference_material_returns_error_not_crash():
    app = make_app(knowledge_base=StubKnowledgeBase([]))
    client = app.test_client()

    resp = client.post("/api/new_question", json={"topic": "nonexistent"})
    data = resp.get_json()

    assert resp.status_code == 200
    assert data == {"error": "No reference material found for topic 'nonexistent'."}


def test_submit_answer_without_active_question_returns_error():
    app = make_app()
    client = app.test_client()

    resp = client.post("/api/submit_answer", json={"choice": "A"})
    data = resp.get_json()

    assert resp.status_code == 200
    assert data == {"error": "No active question. Request a new question first."}


def test_submit_answer_rejects_invalid_choice():
    app = make_app(responses=[VALID_QUESTION_JSON])
    client = app.test_client()

    client.post("/api/new_question", json={"topic": "operations"})
    resp = client.post("/api/submit_answer", json={"choice": "Z"})

    assert resp.status_code == 400
    assert "A, B, C, D" in resp.get_json()["error"]

    # The agent/LLM was never invoked for the bad choice — the question is
    # still pending.
    score = client.get("/api/score").get_json()
    assert score["has_active_question"] is True


def test_unexpected_exception_returns_500_via_global_handler():
    # Deliberately NOT setting app.config["TESTING"] = True — Flask's
    # PROPAGATE_EXCEPTIONS defaults on with TESTING/DEBUG, which would let
    # this exception escape the test client instead of hitting the
    # registered error handler.
    app = create_app(llm_client=MockClient(), knowledge_base=ExplodingKnowledgeBase())
    client = app.test_client()

    resp = client.post("/api/new_question", json={"topic": "operations"})

    assert resp.status_code == 500
    assert "logs/agent.log" in resp.get_json()["error"]
