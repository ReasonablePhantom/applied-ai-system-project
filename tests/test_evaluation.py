"""Regression tests for the quantitative evaluation harness itself.

These exercise the real KnowledgeBase (no LLM call) so a future edit to a
doc or to TOPIC_QUERIES that breaks retrieval routing fails a test, not just
a manual eyeball of evaluation.py's output.
"""

from evaluation import EXPECTED_SOURCES, OFFLINE_FIXTURES, evaluate_retrieval
from retrieval import KnowledgeBase


def test_retrieval_hit_rate_is_perfect_on_real_docs():
    kb = KnowledgeBase()
    hit_rate, results = evaluate_retrieval(kb)

    assert hit_rate == 1.0
    for r in results:
        assert r["hit"], f"topic {r['topic']!r} did not retrieve {r['expected_source']!r}"


def test_offline_fixtures_cover_every_expected_topic():
    assert set(OFFLINE_FIXTURES.keys()) == set(EXPECTED_SOURCES.keys())
    for topic, responses in OFFLINE_FIXTURES.items():
        assert len(responses) >= 1, f"topic {topic!r} has no recorded fixture responses"
