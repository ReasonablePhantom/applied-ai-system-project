from schema_validator import validate_question

VALID_QUESTION = {
    "question": "What is the maximum altitude for a small UAS under Part 107?",
    "choices": {
        "A": "400 feet AGL",
        "B": "500 feet AGL",
        "C": "1,000 feet AGL",
        "D": "There is no altitude limit",
    },
    "correct_answer": "A",
    "explanation": "Part 107 caps altitude at 400 feet above ground level.",
    "citation": "OPERATIONS.md",
}


def test_valid_question_passes():
    is_valid, errors = validate_question(VALID_QUESTION)
    assert is_valid
    assert errors == []


def test_missing_question_text_fails():
    question = dict(VALID_QUESTION)
    question["question"] = ""
    is_valid, errors = validate_question(question)
    assert not is_valid
    assert any("question" in e for e in errors)


def test_missing_choice_key_fails():
    question = dict(VALID_QUESTION)
    question["choices"] = {"A": "400 feet AGL", "B": "500 feet AGL", "C": "1,000 feet AGL"}
    is_valid, errors = validate_question(question)
    assert not is_valid
    assert any("choices missing keys" in e for e in errors)


def test_invalid_correct_answer_fails():
    question = dict(VALID_QUESTION)
    question["correct_answer"] = "E"
    is_valid, errors = validate_question(question)
    assert not is_valid
    assert any("correct_answer" in e for e in errors)


def test_missing_citation_fails():
    question = dict(VALID_QUESTION)
    question["citation"] = ""
    is_valid, errors = validate_question(question)
    assert not is_valid
    assert any("citation" in e for e in errors)


def test_non_dict_input_fails():
    is_valid, errors = validate_question("not a dict")
    assert not is_valid
    assert errors == ["question is not a JSON object"]
