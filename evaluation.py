"""Automated reliability + retrieval evaluation harness.

Produces quantitative, structured evidence that the system works, rather
than relying on someone eyeballing a demo run. Two independent
measurements, each written to eval_results.json and EVALUATION_RESULTS.md:

  1. Retrieval evaluation - does retrieve_by_topic() return chunks from the
     expected source document for each of the four practice topics? No LLM
     call; fully deterministic; always runs.
  2. Generation reliability evaluation - run each topic's practice-question
     generation through the full agent pipeline (schema validation +
     grounding check + retry), and record schema validity, grounding
     confidence score, and attempts used. By default this runs against a
     fixed set of recorded LLM responses (OFFLINE_FIXTURES below) so the
     report is reproducible without an API key, and deliberately includes
     one topic where the first two recorded responses are bad (one fails
     schema validation, one is a plausible-sounding hallucination) so the
     report demonstrates the reliability layer catching both failure modes,
     not just a run where everything happens to succeed. Pass --live to
     additionally exercise the real Gemini API for one question per topic.
"""

import argparse
import datetime
import json
import logging
import os

from faa_agent import FAAAgent
from llm_client import GeminiClient, MockClient
from logging_config import setup_logging
from retrieval import KnowledgeBase

logger = logging.getLogger(__name__)

REPORT_JSON_PATH = os.path.join(os.path.dirname(__file__), "eval_results.json")
REPORT_MD_PATH = os.path.join(os.path.dirname(__file__), "EVALUATION_RESULTS.md")

EXPECTED_SOURCES = {
    "airspace": "AIRSPACE.md",
    "weather": "WEATHER.md",
    "operations": "OPERATIONS.md",
    "certification": "CERTIFICATION_AND_REGISTRATION.md",
}

# Fixed, recorded LLM responses for the deterministic offline reliability
# evaluation. Each topic maps to a list of responses consumed in order by
# MockClient, i.e. what the agent would see on attempt 1, 2, 3, ... The
# "weather" sequence is deliberately adversarial: attempt 1 fails schema
# validation (missing required fields), attempt 2 passes schema but cites a
# document that was never retrieved for this topic (the grounding checker
# must catch the mismatch), and attempt 3 is a genuinely grounded question.
OFFLINE_FIXTURES = {
    "airspace": [
        json.dumps(
            {
                "question": "In which class of airspace may a remote pilot operate without prior ATC authorization?",
                "choices": {"A": "Class G", "B": "Class B", "C": "Class C", "D": "Class D"},
                "correct_answer": "A",
                "explanation": (
                    "Class G is uncontrolled airspace. A remote pilot may operate "
                    "in Class G airspace without prior air traffic control (ATC) "
                    "authorization."
                ),
                "citation": "AIRSPACE.md",
            }
        )
    ],
    "weather": [
        # Attempt 1: fails schema validation (missing correct_answer, explanation, citation).
        json.dumps(
            {
                "question": "What is the minimum flight visibility required under Part 107?",
                "choices": {"A": "1 statute mile", "B": "3 statute miles", "C": "5 statute miles", "D": "10 statute miles"},
            }
        ),
        # Attempt 2: passes schema, fails grounding — cites a document that
        # was never retrieved for this topic (a realistic LLM mistake:
        # attributing a fact to the wrong source). Caught deterministically
        # by the citation check, not by wording overlap, which is the more
        # reliable of the two grounding signals — see the "Known
        # Limitations" note in model_card.md on why overlap alone can be
        # fooled by incidental shared vocabulary.
        json.dumps(
            {
                "question": "What is the minimum flight visibility required under Part 107?",
                "choices": {"A": "1 statute mile", "B": "3 statute miles", "C": "5 statute miles", "D": "10 statute miles"},
                "correct_answer": "B",
                "explanation": "Minimum flight visibility is 3 statute miles.",
                "citation": "OPERATIONS.md",
            }
        ),
        # Attempt 3: passes both checks.
        json.dumps(
            {
                "question": "What is the minimum flight visibility required under Part 107?",
                "choices": {"A": "1 statute mile", "B": "3 statute miles", "C": "5 statute miles", "D": "10 statute miles"},
                "correct_answer": "B",
                "explanation": (
                    "Minimum flight visibility is 3 statute miles, one of the key "
                    "weather minimums for small unmanned aircraft operations."
                ),
                "citation": "WEATHER.md",
            }
        ),
    ],
    "operations": [
        json.dumps(
            {
                "question": "What is the maximum altitude for a small UAS under Part 107 (away from a structure)?",
                "choices": {"A": "400 feet AGL", "B": "500 feet AGL", "C": "1,000 feet AGL", "D": "There is no limit"},
                "correct_answer": "A",
                "explanation": (
                    "Max altitude is 400 ft AGL (or 400 ft above a nearby structure) "
                    "under Part 107 operating rules."
                ),
                "citation": "OPERATIONS.md",
            }
        )
    ],
    "certification": [
        json.dumps(
            {
                "question": "How often must a Remote Pilot Certificate be renewed?",
                "choices": {"A": "Every 24 months", "B": "Every 12 months", "C": "Every 5 years", "D": "It never expires"},
                "correct_answer": "A",
                "explanation": (
                    "The Remote Pilot Certificate must be renewed by passing a "
                    "recurrent knowledge test (or completing FAA-approved recurrent "
                    "online training) every 24 calendar months."
                ),
                "citation": "CERTIFICATION_AND_REGISTRATION.md",
            }
        )
    ],
}


def evaluate_retrieval(kb, top_k=3):
    """No LLM call: does keyword retrieval route each topic to its expected
    source document? Returns (hit_rate, results)."""
    results = []
    hits = 0
    for topic, expected_file in EXPECTED_SOURCES.items():
        retrieved = kb.retrieve_by_topic(topic, top_k=top_k)
        retrieved_files = [f for f, _ in retrieved]
        hit = expected_file in retrieved_files
        hits += int(hit)
        results.append(
            {
                "topic": topic,
                "expected_source": expected_file,
                "retrieved_sources": retrieved_files,
                "hit": hit,
            }
        )
    hit_rate = hits / len(EXPECTED_SOURCES)
    logger.info("Retrieval evaluation: hit_rate=%.2f", hit_rate)
    return hit_rate, results


def evaluate_generation(kb, llm_client_factory, mode):
    """Run new_question() for every topic through a fresh agent, recording
    schema/grounding outcome, confidence score, and attempts used.
    llm_client_factory(topic) -> an llm_client for that topic's run."""
    results = []
    successes = 0
    confidence_scores = []
    for topic in EXPECTED_SOURCES:
        agent = FAAAgent(llm_client=llm_client_factory(topic), knowledge_base=kb)
        result = agent.new_question(topic)
        success = "error" not in result
        confidence = result.get("confidence_score")
        results.append(
            {
                "topic": topic,
                "success": success,
                "confidence_score": confidence,
                "attempts_used": agent.last_attempts_used,
                "error": result.get("error"),
            }
        )
        if success:
            successes += 1
            if confidence is not None:
                confidence_scores.append(confidence)
        logger.info(
            "Generation evaluation [%s] topic=%r success=%s attempts=%s confidence=%s",
            mode, topic, success, agent.last_attempts_used, confidence,
        )

    success_rate = successes / len(results) if results else 0.0
    avg_confidence = (
        sum(confidence_scores) / len(confidence_scores) if confidence_scores else None
    )
    return success_rate, avg_confidence, results


def _offline_client_factory(topic):
    return MockClient(responses=OFFLINE_FIXTURES[topic])


def _live_client_factory(_topic):
    return GeminiClient()


def render_markdown(generated_at, retrieval_hit_rate, retrieval_results, generation_mode, generation_success_rate, avg_confidence, generation_results):
    lines = [
        "# Evaluation Results",
        "",
        f"Generated: {generated_at}",
        "",
        "## Retrieval Evaluation",
        "",
        "No LLM call — does keyword retrieval route each topic to its expected source document?",
        "",
        "| Topic | Expected Source | Retrieved Sources | Hit |",
        "|---|---|---|---|",
    ]
    for r in retrieval_results:
        lines.append(
            f"| {r['topic']} | {r['expected_source']} | {', '.join(sorted(set(r['retrieved_sources'])))} | "
            f"{'✅' if r['hit'] else '❌'} |"
        )
    lines += [
        "",
        f"**Hit rate: {retrieval_hit_rate:.0%}**",
        "",
        f"## Generation Reliability Evaluation (mode: {generation_mode})",
        "",
        "| Topic | Success | Confidence Score | Attempts Used | Error |",
        "|---|---|---|---|---|",
    ]
    for r in generation_results:
        confidence = r["confidence_score"] if r["confidence_score"] is not None else "—"
        error = r["error"] or "—"
        lines.append(
            f"| {r['topic']} | {'✅' if r['success'] else '❌'} | {confidence} | "
            f"{r['attempts_used']} | {error} |"
        )
    avg_confidence_str = f"{avg_confidence:.0f}" if avg_confidence is not None else "n/a"
    lines += [
        "",
        f"**Success rate: {generation_success_rate:.0%}**",
        f"**Average confidence score (successful runs): {avg_confidence_str}/100**",
        "",
        "Note: the `weather` topic's offline fixture deliberately queues a "
        "schema-invalid response, then a schema-valid response that cites a "
        "document never retrieved for this topic, before a grounded "
        "response, to demonstrate that both validation layers actually "
        "reject bad output rather than always passing on the first try. See "
        "OFFLINE_FIXTURES in evaluation.py.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true",
        help="Also run generation evaluation against the real Gemini API (requires GEMINI_API_KEY).",
    )
    args = parser.parse_args()

    setup_logging()

    kb = KnowledgeBase()
    retrieval_hit_rate, retrieval_results = evaluate_retrieval(kb)

    if args.live:
        try:
            GeminiClient()  # fail fast with a clear message if no API key
        except RuntimeError as e:
            print(f"[fatal] --live requires a working Gemini client: {e}")
            return
        mode = "live"
        client_factory = _live_client_factory
    else:
        mode = "offline fixtures"
        client_factory = _offline_client_factory

    generation_success_rate, avg_confidence, generation_results = evaluate_generation(
        kb, client_factory, mode
    )

    generated_at = datetime.datetime.now().isoformat(timespec="seconds")
    report = {
        "generated_at": generated_at,
        "retrieval_evaluation": {
            "hit_rate": retrieval_hit_rate,
            "results": retrieval_results,
        },
        "generation_evaluation": {
            "mode": mode,
            "success_rate": generation_success_rate,
            "average_confidence_score": avg_confidence,
            "results": generation_results,
        },
    }

    with open(REPORT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    markdown = render_markdown(
        generated_at, retrieval_hit_rate, retrieval_results,
        mode, generation_success_rate, avg_confidence, generation_results,
    )
    with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(markdown)
    print(f"Wrote {REPORT_JSON_PATH} and {REPORT_MD_PATH}")


if __name__ == "__main__":
    main()
