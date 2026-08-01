"""In-memory session state: the active question and running score/history."""


class SessionStore:
    def __init__(self):
        self.current_question = None
        self.current_retrieved_chunks = []
        self.history = []
        self.score = {"correct": 0, "total": 0}

    def has_active_question(self):
        return self.current_question is not None

    def store_question(self, question, retrieved_chunks):
        self.current_question = question
        self.current_retrieved_chunks = retrieved_chunks

    def record_answer(self, user_choice, is_correct):
        self.history.append(
            {
                "question": self.current_question["question"],
                "user_choice": user_choice,
                "correct_answer": self.current_question["correct_answer"],
                "correct": is_correct,
            }
        )
        self.score["total"] += 1
        if is_correct:
            self.score["correct"] += 1
        self.current_question = None
        self.current_retrieved_chunks = []

    def get_score_summary(self):
        total = self.score["total"]
        correct = self.score["correct"]
        pct = (correct / total * 100) if total else 0.0
        return f"{correct}/{total} correct ({pct:.0f}%)"
