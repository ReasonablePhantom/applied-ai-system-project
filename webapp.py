"""Flask web UI for the FAA Part 107 Exam Prep Agent.

A local-only browser alternative to main.py — same FAAAgent/KnowledgeBase/
GeminiClient backend, no new AI logic here, just routes + per-session state
so multiple browser tabs each get their own question/score without
stepping on each other. Not designed for public/multi-user deployment; see
model_card.md's Misuse Prevention Measures.
"""

import logging
import os
import secrets
import sys
import threading
import uuid

from flask import Flask, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException

from faa_agent import FAAAgent
from llm_client import GeminiClient
from logging_config import setup_logging
from retrieval import KnowledgeBase

logger = logging.getLogger(__name__)

TOPICS = ("airspace", "weather", "operations", "certification")
VALID_CHOICES = {"A", "B", "C", "D"}


def create_app(llm_client=None, knowledge_base=None):
    """App factory. llm_client is required (no default) so a missing API
    key fails fast at startup — see the __main__ block below — rather than
    lazily inside a request handler. Tests pass llm_client=MockClient(...)."""
    if llm_client is None:
        raise ValueError(
            "create_app() requires an llm_client (e.g. GeminiClient() for "
            "production or MockClient(...) for tests) — it will not "
            "silently construct one."
        )

    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "").strip() or secrets.token_hex(32)

    kb = knowledge_base or KnowledgeBase()
    app.agents = {}
    agents_lock = threading.Lock()

    def get_agent():
        if "session_id" not in session:
            session["session_id"] = uuid.uuid4().hex
        sid = session["session_id"]
        with agents_lock:
            if sid not in app.agents:
                app.agents[sid] = FAAAgent(llm_client=llm_client, knowledge_base=kb)
            return app.agents[sid]

    @app.route("/")
    def index():
        return render_template("index.html", topics=TOPICS)

    @app.route("/api/new_question", methods=["POST"])
    def new_question():
        data = request.get_json(silent=True) or {}
        topic = (data.get("topic") or "operations").strip().lower()
        agent = get_agent()
        result = agent.new_question(topic)
        return jsonify(result)

    @app.route("/api/submit_answer", methods=["POST"])
    def submit_answer():
        data = request.get_json(silent=True) or {}
        choice = (data.get("choice") or "").strip().upper()
        if choice not in VALID_CHOICES:
            return jsonify({"error": "choice must be one of A, B, C, D"}), 400
        agent = get_agent()
        result = agent.submit_answer(choice)
        return jsonify(result)

    @app.route("/api/score")
    def score():
        agent = get_agent()
        return jsonify(
            {
                "score": agent.session.get_score_summary(),
                "has_active_question": agent.session.has_active_question(),
            }
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        if isinstance(e, HTTPException):
            return e
        logger.exception("Unexpected error handling %s %s", request.method, request.path)
        return (
            jsonify({"error": "Something went wrong handling that request. See logs/agent.log for details."}),
            500,
        )

    return app


if __name__ == "__main__":
    setup_logging()
    try:
        client = GeminiClient()
    except RuntimeError as e:
        logger.error("Startup failed: %s", e)
        print(f"\n[fatal] {e}")
        sys.exit(1)

    app = create_app(llm_client=client)
    port = int(os.getenv("WEBAPP_PORT", "5000"))
    print(f"FAA Part 107 Exam Prep Agent — open http://127.0.0.1:{port}/")
    app.run(host="127.0.0.1", port=port, debug=False)
