from reliability.grounding_checker import check_feedback_grounding, check_question_grounding

RETRIEVED = [
    (
        "OPERATIONS.md",
        "A small unmanned aircraft may not be flown higher than 400 feet "
        "above ground level (AGL), unless it remains within a 400-foot "
        "radius of a structure.",
    )
]


def test_grounded_question_is_low_risk():
    question = {
        "citation": "OPERATIONS.md",
        "explanation": "Part 107 caps altitude at 400 feet above ground level (AGL) for small unmanned aircraft.",
    }
    result = check_question_grounding(question, RETRIEVED)
    assert result["level"] == "low"
    assert result["needs_regeneration"] is False


def test_wrong_citation_is_flagged():
    question = {
        "citation": "WEATHER.md",
        "explanation": "Part 107 caps altitude at 400 feet above ground level (AGL) for small unmanned aircraft.",
    }
    result = check_question_grounding(question, RETRIEVED)
    assert result["needs_regeneration"] is True
    assert any("does not match" in reason for reason in result["reasons"])


def test_hallucinated_explanation_is_flagged():
    question = {
        "citation": "OPERATIONS.md",
        "explanation": "Drones must always carry a fire extinguisher and a spare battery pack.",
    }
    result = check_question_grounding(question, RETRIEVED)
    assert result["needs_regeneration"] is True


def test_missing_explanation_is_flagged():
    question = {"citation": "OPERATIONS.md", "explanation": ""}
    result = check_question_grounding(question, RETRIEVED)
    assert result["needs_regeneration"] is True
    assert any("no explanation" in reason for reason in result["reasons"])


def test_feedback_grounding_passes_when_overlapping():
    feedback = "Part 107 caps altitude at 400 feet above ground level (AGL)."
    result = check_feedback_grounding(feedback, RETRIEVED)
    assert result["level"] == "low"


def test_feedback_grounding_fails_when_hallucinated():
    feedback = "You must always fly below 50 feet near airports regardless of clearance."
    result = check_feedback_grounding(feedback, RETRIEVED)
    assert result["needs_regeneration"] is True
