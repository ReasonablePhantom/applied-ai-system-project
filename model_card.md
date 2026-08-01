# Model Card — FAA Part 107 Exam Prep Agent

## Overview

This system is an agent that helps a candidate study for the FAA Part 107
(Small Unmanned Aircraft) remote pilot knowledge test. It generates
multiple-choice practice questions on request and grades the candidate's
selected answer, explaining the correct answer with a citation back to the
source material. See [diagrams/architecture.md](diagrams/architecture.md)
for the full data-flow and component diagram.

## Intended Use

Practice-question generation and self-assessment for someone studying for
the Part 107 knowledge test. It is a study aid, not a substitute for the
FAA's own test prep materials or an FAA-approved test.

## Core AI Component

An **agent** (`faa_agent.FAAAgent`) that routes each request to one of two
flows and, in both, runs the LLM's output back through validation before it
reaches the user:

- **New question**: retrieve reference text on the requested topic → LLM
  drafts a question grounded in that text → structural validation → a
  grounding check that a fresh LLM draft must pass before it is shown to the
  user.
- **Submit answer**: grade the stored answer → LLM drafts feedback grounded
  in the same retrieved text → the same grounding check, falling back to the
  original (already-validated) explanation if the fresh feedback fails.

## Knowledge Source

`docs/` contains four short reference documents distilled from 14 CFR Part
107: airspace classification and authorization, weather minimums, operating
rules, and certification/registration. `retrieval.py` chunks these on
markdown headers and retrieves by keyword overlap (`TOPIC_QUERIES` maps the
four practice topics — airspace, weather, operations, certification — to
retrieval queries). This is intentionally a small, fixed reference set: it
is a course project and not a claim of complete or current FAA regulatory
coverage. **This system is a study aid, not a source of authoritative or
current FAA guidance** — always verify against the FAA's own published
Part 107 materials before test day.

## Why It's Trustworthy: the Reliability Layer

The core risk with an LLM-driven quiz generator is hallucination: a
plausible-sounding but factually wrong question, answer, or explanation.
Two independent checks guard against this before any LLM output reaches the
user:

1. **Schema validation** (`schema_validator.py`) — the generated question
   must have exactly one correct answer, four non-empty choices, and a
   citation. Malformed output is rejected outright.
2. **Grounding check** (`reliability/grounding_checker.py`) — the cited
   source must be one of the documents actually retrieved for this
   question, and the explanation's wording must substantially overlap with
   the retrieved reference text (not just assert a conclusion). This is a
   simple keyword-overlap heuristic, not semantic entailment — it catches
   answers that ignore the retrieved context entirely, but it will not
   catch a subtle factual error stated in vocabulary that happens to overlap
   the source text.

If either check fails, the agent discards the draft and asks the LLM to try
again, up to `max_generation_attempts` (default 3). If no attempt passes
after that many tries, the agent reports failure explicitly rather than
showing an ungrounded question. The same grounding check applies to
answer-grading feedback; a failed check there falls back to the question's
own explanation, which is already known to have passed grounding.

## Logging and Error Handling

`errors.py` defines typed exceptions (`RetrievalError`, `GenerationFailedError`,
`NoActiveQuestionError`) that the orchestrator raises internally for each
failure mode in the retry loop above, instead of relying on ad hoc `None` or
empty-string sentinels. `FAAAgent.new_question` / `submit_answer` catch these
at the boundary and convert them into the `{"error": ...}` dict contract the
CLI (and the diagrams/architecture.md Output Formatter) expect — callers
never see a raised exception, but every failure is still logged with the
reason.

`logging_config.py` configures a console handler (INFO+, what a user running
the CLI sees) and a file handler (`logs/agent.log`, DEBUG+) so every retry
attempt's specific failure reason — a parse error, a schema violation, a
grounding failure — is recorded even though the CLI only prints a summary.
Gemini API exceptions are logged (with traceback) in `llm_client.py` before
being converted to an empty completion, so a live-traffic failure is visible
in the log even though the retry loop treats it the same as any other failed
attempt.

## Known Limitations

- **Keyword-overlap retrieval and grounding**, not embeddings or semantic
  similarity. Both can be fooled by paraphrases that reuse few of the same
  words, or pass content that overlaps in wording but not in meaning.
- **Small, hand-curated knowledge base.** Four documents covering four
  topics is enough to demonstrate the architecture, not the full breadth of
  the real Part 107 knowledge-test content areas (e.g., loading and
  performance, radio communication procedures, and aeronautical decision-
  making are not covered here).
- **LLM API failures degrade to an empty completion**, not a raised
  exception, in `llm_client.py` — logged (with traceback) but still treated
  as just one failed generation attempt. A persistent outage exhausts
  `max_generation_attempts` and surfaces as the same generic
  "could not generate a grounded question" message as a hallucination
  failure would, rather than a distinguishable "API is down" message — check
  `logs/agent.log` to tell the two apart.
- **No persistence across runs.** `session_store.py` is in-memory only —
  score history resets each time the program restarts.

## Evaluation

`tests/test_schema_validator.py` and `tests/test_grounding_checker.py` are
unit tests against hand-built inputs (valid, malformed, and hallucinated
cases) for the two validation layers. `tests/test_agent_workflow.py` is an
end-to-end test of both flows using `llm_client.MockClient` (queued canned
responses) and a stub knowledge base, so the full retry/validation loop can
be exercised without a live API key — including the case where the first
LLM draft is invalid and the agent must retry.
