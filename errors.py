"""Typed exceptions for the agent's error-handling layer.

FAAAgent's public methods (new_question, submit_answer) still return plain
dicts with an "error" key — that is the Output Formatter contract described
in diagrams/architecture.md. Internally, these exceptions replace ad hoc
None/empty-string sentinels so failures are raised, logged, and handled
explicitly at one boundary instead of silently propagating as malformed data.
"""


class AgentError(Exception):
    """Base class for all errors raised by the agent's core logic."""


class RetrievalError(AgentError):
    """Raised when no reference material could be retrieved for a topic."""


class GenerationFailedError(AgentError):
    """Raised when the agent could not produce a validated, grounded result
    within the allowed number of attempts."""

    def __init__(self, message, last_errors=None):
        super().__init__(message)
        self.last_errors = last_errors or []


class NoActiveQuestionError(AgentError):
    """Raised when an answer is submitted with no question currently stored."""
