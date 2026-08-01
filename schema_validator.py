"""Structural validation for agent-generated quiz questions."""

REQUIRED_CHOICE_KEYS = {"A", "B", "C", "D"}


def validate_question(question):
    """Check a generated question dict against the required shape.

    Returns (is_valid: bool, errors: list[str]).
    """
    errors = []

    if not isinstance(question, dict):
        return False, ["question is not a JSON object"]

    if not question.get("question", "").strip():
        errors.append("missing 'question' text")

    choices = question.get("choices")
    if not isinstance(choices, dict):
        errors.append("missing or malformed 'choices' object")
    else:
        missing_keys = REQUIRED_CHOICE_KEYS - choices.keys()
        if missing_keys:
            errors.append(f"choices missing keys: {sorted(missing_keys)}")
        empty_choices = [k for k in REQUIRED_CHOICE_KEYS & choices.keys() if not str(choices[k]).strip()]
        if empty_choices:
            errors.append(f"choices have empty text: {sorted(empty_choices)}")

    correct_answer = question.get("correct_answer")
    if correct_answer not in REQUIRED_CHOICE_KEYS:
        errors.append("'correct_answer' must be exactly one of A, B, C, D")

    if not question.get("explanation", "").strip():
        errors.append("missing 'explanation'")

    if not question.get("citation", "").strip():
        errors.append("missing 'citation' to a source document")

    return len(errors) == 0, errors
