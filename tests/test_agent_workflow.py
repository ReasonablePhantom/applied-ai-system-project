import json

from faa_agent import FAAAgent
from llm_client import MockClient

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

INVALID_QUESTION_JSON = json.dumps(
    {
        "question": "What is the maximum altitude for a small UAS under Part 107?",
        "choices": {"A": "400 feet AGL", "B": "500 feet AGL"},
        # missing correct_answer, explanation, citation
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

HALLUCINATED_FEEDBACK_JSON = json.dumps(
    {"feedback": "Drones must always carry a spare battery and a fire extinguisher."}
)


class StubKnowledgeBase:
    """Deterministic stand-in for retrieval.KnowledgeBase in agent tests."""

    def __init__(self, chunks):
        self.chunks = chunks

    def retrieve_by_topic(self, topic, top_k=3):
        return self.chunks


def make_agent(responses):
    return FAAAgent(
        llm_client=MockClient(responses=responses),
        knowledge_base=StubKnowledgeBase(RETRIEVED_CHUNKS),
    )


def test_new_question_success_on_first_attempt():
    agent = make_agent([VALID_QUESTION_JSON])
    result = agent.new_question("operations")

    assert "error" not in result
    assert result["choices"]["A"] == "400 feet AGL"
    # correct_answer / explanation must NOT be leaked to the display payload
    assert "correct_answer" not in result
    assert "explanation" not in result
    assert agent.session.has_active_question()

    # The explanation is verbatim from the retrieved chunk, so grounding
    # should score it at full confidence.
    assert result["confidence_score"] == 100
    assert agent.last_confidence_score == 100
    assert agent.last_attempts_used == 1


def test_new_question_retries_after_invalid_json_then_succeeds():
    agent = make_agent([INVALID_QUESTION_JSON, VALID_QUESTION_JSON])
    result = agent.new_question("operations")

    assert "error" not in result
    assert agent.session.has_active_question()
    # Proves the retry loop actually re-tries rather than accepting attempt 1.
    assert agent.last_attempts_used == 2


def test_new_question_fails_after_max_attempts_of_bad_output():
    agent = make_agent([INVALID_QUESTION_JSON] * 3)
    result = agent.new_question("operations")

    assert "error" in result
    assert not agent.session.has_active_question()
    assert agent.last_attempts_used == 3
    assert agent.last_confidence_score is None


def test_submit_correct_answer():
    agent = make_agent([VALID_QUESTION_JSON, VALID_FEEDBACK_JSON])
    agent.new_question("operations")
    result = agent.submit_answer("a")

    assert result["correct"] is True
    assert result["correct_answer"] == "A"
    assert result["citation"] == "OPERATIONS.md"
    assert "400 feet" in result["feedback"]
    assert result["feedback_confidence_score"] == 100
    assert not agent.session.has_active_question()


def test_submit_incorrect_answer():
    agent = make_agent([VALID_QUESTION_JSON, VALID_FEEDBACK_JSON])
    agent.new_question("operations")
    result = agent.submit_answer("b")

    assert result["correct"] is False
    assert result["correct_answer"] == "A"


def test_submit_answer_without_active_question_errors():
    agent = make_agent([])
    result = agent.submit_answer("a")

    assert "error" in result


def test_submit_answer_falls_back_to_stored_explanation_when_feedback_ungrounded():
    agent = make_agent([VALID_QUESTION_JSON, HALLUCINATED_FEEDBACK_JSON])
    agent.new_question("operations")
    result = agent.submit_answer("a")

    assert result["correct"] is True
    # Hallucinated feedback must be discarded in favor of the question's own,
    # already-grounded explanation.
    assert "fire extinguisher" not in result["feedback"]
    assert "400 feet" in result["feedback"]
    # Confidence falls back to the question's own (already-passed) score,
    # rather than reporting a score for the rejected draft.
    assert result["feedback_confidence_score"] == 100
