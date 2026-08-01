"""Agent Orchestrator for the FAA Part 107 exam-prep agent.

Implements the two data flows from diagrams/architecture.md:

  Flow A (new_question):  Retrieval -> Question Generator -> Schema Validator
                           -> Reliability Checker -> Session Store -> Output
  Flow B (submit_answer):  Session Store -> Answer Grader -> Reliability
                           Checker -> Output
"""

import json
import logging
import os
import re

from errors import GenerationFailedError, NoActiveQuestionError, RetrievalError
from reliability.grounding_checker import check_feedback_grounding, check_question_grounding
from retrieval import KnowledgeBase
from schema_validator import validate_question
from session_store import SessionStore

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load_prompt(name):
    with open(os.path.join(PROMPTS_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


def _fill(template, values):
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def _parse_json_object(raw_text):
    """Best-effort JSON parse: strips markdown code fences if the model added
    them despite instructions not to. Returns (obj, error) where error is a
    string describing the failure, or None on success."""
    if not raw_text or not raw_text.strip():
        return None, "empty completion from the LLM"

    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    try:
        return json.loads(text), None
    except json.JSONDecodeError as e:
        return None, f"could not parse JSON from LLM output: {e}"


class FAAAgent:
    """Central intent router: new_question vs submit_answer."""

    def __init__(self, llm_client, knowledge_base=None, session_store=None, max_generation_attempts=3):
        self.llm = llm_client
        self.kb = knowledge_base or KnowledgeBase()
        self.session = session_store or SessionStore()
        self.max_attempts = max_generation_attempts

    def new_question(self, topic="operations"):
        """Flow A. Returns a display-safe dict on success, or {"error": ...,
        "last_errors": [...]} on failure — never raises."""
        try:
            question, retrieved = self._generate_question(topic)
        except RetrievalError as e:
            logger.warning("new_question(topic=%r): %s", topic, e)
            return {"error": str(e)}
        except GenerationFailedError as e:
            logger.warning("new_question(topic=%r): %s (reasons=%s)", topic, e, e.last_errors)
            return {"error": str(e), "last_errors": e.last_errors}

        self.session.store_question(question, retrieved)
        logger.info("new_question(topic=%r): stored a validated, grounded question", topic)
        return self._format_question_for_display(question)

    def _generate_question(self, topic):
        """Retrieval -> Question Generator -> Schema Validator -> Reliability
        Checker, looping until a grounded question is produced or attempts
        run out. Raises RetrievalError / GenerationFailedError on failure."""
        retrieved = self.kb.retrieve_by_topic(topic)
        if not retrieved:
            raise RetrievalError(f"No reference material found for topic '{topic}'.")

        context = "\n\n".join(f"[{filename}]\n{text}" for filename, text in retrieved)
        system_prompt = _load_prompt("question_generator_system.txt")
        user_prompt = _fill(
            _load_prompt("question_generator_user.txt"),
            {"TOPIC": topic, "CONTEXT": context},
        )

        last_errors = []
        for attempt in range(1, self.max_attempts + 1):
            raw = self.llm.complete(system_prompt, user_prompt)
            question, parse_error = _parse_json_object(raw)
            if parse_error:
                logger.debug("new_question attempt %d/%d: %s", attempt, self.max_attempts, parse_error)
                last_errors = [parse_error]
                continue

            is_valid, schema_errors = validate_question(question)
            if not is_valid:
                logger.debug(
                    "new_question attempt %d/%d: schema errors: %s",
                    attempt, self.max_attempts, schema_errors,
                )
                last_errors = schema_errors
                continue

            grounding = check_question_grounding(question, retrieved)
            if grounding["needs_regeneration"]:
                logger.debug(
                    "new_question attempt %d/%d: grounding failed: %s",
                    attempt, self.max_attempts, grounding["reasons"],
                )
                last_errors = grounding["reasons"]
                continue

            return question, retrieved

        raise GenerationFailedError(
            f"Could not generate a reliably grounded question about "
            f"'{topic}' after {self.max_attempts} attempts.",
            last_errors=last_errors,
        )

    def submit_answer(self, user_choice):
        """Flow B. Returns a feedback dict on success, or {"error": ...} if
        there is no active question — never raises."""
        try:
            question = self._require_active_question()
        except NoActiveQuestionError as e:
            logger.warning("submit_answer: %s", e)
            return {"error": str(e)}

        retrieved = self.session.current_retrieved_chunks
        choice = user_choice.strip().upper()
        correct_answer = question["correct_answer"]
        is_correct = choice == correct_answer

        feedback = self._generate_feedback(question, choice, retrieved)

        grounding = check_feedback_grounding(feedback, retrieved)
        if grounding["needs_regeneration"]:
            # Fall back to the question's own explanation, which already
            # passed grounding validation when the question was generated.
            logger.debug("submit_answer: feedback failed grounding (%s); using stored explanation", grounding["reasons"])
            feedback = question["explanation"]

        self.session.record_answer(choice, is_correct)
        logger.info("submit_answer: choice=%s correct=%s", choice, is_correct)

        return {
            "correct": is_correct,
            "correct_answer": correct_answer,
            "feedback": feedback,
            "citation": question["citation"],
            "score": self.session.get_score_summary(),
        }

    def _require_active_question(self):
        if not self.session.has_active_question():
            raise NoActiveQuestionError("No active question. Request a new question first.")
        return self.session.current_question

    def _generate_feedback(self, question, user_choice, retrieved):
        context = "\n\n".join(f"[{filename}]\n{text}" for filename, text in retrieved)
        system_prompt = _load_prompt("answer_grader_system.txt")
        user_prompt = _fill(
            _load_prompt("answer_grader_user.txt"),
            {
                "QUESTION": question["question"],
                "CHOICES": json.dumps(question["choices"]),
                "CORRECT_ANSWER": question["correct_answer"],
                "USER_CHOICE": user_choice,
                "CONTEXT": context,
            },
        )
        raw = self.llm.complete(system_prompt, user_prompt)
        feedback_obj, parse_error = _parse_json_object(raw)
        if parse_error or not isinstance(feedback_obj, dict):
            return question["explanation"]
        return feedback_obj.get("feedback", question["explanation"])

    @staticmethod
    def _format_question_for_display(question):
        """Withhold the correct answer and explanation until the user answers."""
        return {
            "question": question["question"],
            "choices": question["choices"],
        }
