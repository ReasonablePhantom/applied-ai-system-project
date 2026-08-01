"""Reliability layer: checks whether generated content is actually grounded
in the retrieved Part 107 source text, rather than hallucinated.

Mirrors the shape of the risk_assessor used elsewhere in this course: a pure
function that returns a score, a risk level, and human-readable reasons.
"""

import re


def _tokenize(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _overlap_ratio(text, context_words):
    words = _tokenize(text)
    if not words:
        return 0.0
    return len(words & context_words) / len(words)


def check_question_grounding(question, retrieved_chunks):
    """Assess a freshly generated question's citation and explanation against
    the retrieved source chunks used to generate it.

    Returns {score, level, reasons, needs_regeneration}. `level` follows the
    same convention as elsewhere in this course: "low" risk permits use as-is,
    "medium"/"high" risk means the caller should regenerate.
    """
    reasons = []
    score = 100

    retrieved_filenames = {filename for filename, _ in retrieved_chunks}
    context_words = _tokenize(" ".join(text for _, text in retrieved_chunks))

    citation = question.get("citation", "")
    if not citation:
        score -= 30
        reasons.append("question has no citation to a source document")
    elif citation not in retrieved_filenames:
        score -= 40
        reasons.append(
            f"citation '{citation}' does not match any retrieved source {sorted(retrieved_filenames)}"
        )

    explanation = question.get("explanation", "")
    if not explanation:
        score -= 50
        reasons.append("question has no explanation")
    else:
        ratio = _overlap_ratio(explanation, context_words)
        if ratio < 0.25:
            score -= 30
            reasons.append(f"explanation has low overlap with retrieved source text ({ratio:.0%})")

    score = max(score, 0)
    level = "low" if score >= 80 else "medium" if score >= 50 else "high"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "needs_regeneration": level != "low",
    }


def check_feedback_grounding(feedback_explanation, retrieved_chunks):
    """Assess whether answer-grading feedback is grounded in the retrieved
    source chunks for the question being graded."""
    reasons = []
    score = 100
    context_words = _tokenize(" ".join(text for _, text in retrieved_chunks))

    if not feedback_explanation or not feedback_explanation.strip():
        score -= 50
        reasons.append("feedback has no explanation")
    else:
        ratio = _overlap_ratio(feedback_explanation, context_words)
        if ratio < 0.25:
            score -= 40
            reasons.append(f"feedback has low overlap with retrieved source text ({ratio:.0%})")

    score = max(score, 0)
    level = "low" if score >= 80 else "medium" if score >= 50 else "high"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "needs_regeneration": level != "low",
    }
