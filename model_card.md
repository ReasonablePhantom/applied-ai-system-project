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
   question, and the explanation's content-word overlap with the retrieved
   reference text must clear a threshold (not just assert a conclusion).
   This is a keyword-overlap heuristic, not semantic entailment — see
   "Known Limitations" below for what it does and doesn't catch.

If either check fails, the agent discards the draft and asks the LLM to try
again, up to `max_generation_attempts` (default 3). If no attempt passes
after that many tries, the agent reports failure explicitly rather than
showing an ungrounded question. The same grounding check applies to
answer-grading feedback; a failed check there falls back to the question's
own explanation, which is already known to have passed grounding.

### Confidence Scoring

The grounding check doesn't just pass/fail internally — its 0–100 score
(citation match + content-word overlap ratio, thresholded at 80/50 into
low/medium/high risk) is surfaced as a first-class field on the agent's
output, not just logged:

- `new_question()` includes `confidence_score` in the display payload (the
  grounding score of the question that was ultimately accepted).
- `submit_answer()` includes `feedback_confidence_score` — the grounding
  score of the LLM-drafted feedback, or the question's own confidence score
  if that draft was rejected and the stored explanation was used instead.
- `FAAAgent.last_attempts_used` / `last_confidence_score` expose the same
  numbers programmatically, which is what `evaluation.py` reads to build
  the quantitative report described below.

A user (or a grader) can see, per question, not just an answer but *how
confidently grounded* that answer is — and the CLI prints both scores
alongside every question and every feedback message.

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
  words, or content that overlaps in wording but not in meaning. Even after
  the stopword fix (see "Unexpected Findings During Testing" below), a
  fabricated claim built from genuinely domain-relevant nouns could still
  slip through — content-word overlap is a proxy for groundedness, not a
  guarantee of it.
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

## Biases

- **Knowledge-base topic coverage bias.** The four hand-written reference
  docs were chosen (and written) by the developer, not sourced verbatim
  from the FAA. They emphasize the topics that felt most demonstrable for
  this project (airspace, weather, operating rules, certification) and
  entirely omit other real Part 107 knowledge-test areas — loading and
  performance, radio communication procedures, airport operations,
  aeronautical decision-making. A user who only studies with this tool will
  develop uneven topic coverage that does not reflect the real exam's
  weighting.
- **Paraphrase bias in the reference docs themselves.** The docs are the
  developer's (Claude's) summary of 14 CFR Part 107 content, not the
  regulation text or FAA-published study material verbatim. Any
  simplification, omission, or subtly imprecise paraphrase in
  `docs/*.md` becomes the "ground truth" the grounding checker validates
  against — the reliability layer proves output is *consistent with the
  knowledge base*, not that the knowledge base is itself a complete or
  perfectly accurate restatement of the regulation.
- **LLM phrasing and distractor bias.** Gemini generates the question
  stems, distractor choices, and explanations. Its own training data and
  tendencies shape which distractors it picks (e.g., favoring
  numerically-close wrong answers) and how it phrases explanations — this
  is standard LLM behavior, not something this project's validation layer
  is designed to detect or correct, since schema validation and grounding
  checks assess structure and source-consistency, not stylistic or
  pedagogical quality.
- **English-only.** Retrieval, prompts, and generation all assume English
  input and output; there is no accommodation for non-native English
  speakers, who make up a real share of Part 107 test-takers.

## Misuse Prevention Measures

- **Explicit "study aid, not authoritative source" framing**, stated in
  Overview and Knowledge Source above and repeated in the README — the
  system does not claim to replace the FAA's own materials or guarantee
  exam readiness.
- **Bounded retry cost.** `max_generation_attempts` (default 3) caps how
  many LLM calls a single question or feedback request can trigger,
  preventing an unbounded retry loop from silently running up API cost
  under adversarial or degenerate input.
- **No credential or PII collection.** The CLI takes no login, name, or
  personal data — session state (current question, score) is in-memory
  only and never written to disk or transmitted anywhere beyond the Gemini
  API call itself.
- **API key never leaves local config.** `GEMINI_API_KEY` is read from a
  local `.env` (gitignored) and used only for direct Gemini API calls; nothing
  in this codebase logs, echoes, or transmits it elsewhere.
- **Not designed for untrusted multi-user deployment.** This is a
  single-user local CLI. It has no authentication, no per-user rate
  limiting, and no output moderation beyond the domain-specific grounding
  check — deploying it as a public-facing service without adding those
  would be a misuse of the current design, not a supported use case.
- **The web UI (`webapp.py`) is a local single-process demo, not a
  hardened multi-user service.** It extends the same single-user-oriented
  design to a browser: it binds to `127.0.0.1` only (not reachable over
  the network), has no authentication, no CSRF protection, and no session
  expiry or memory cap — each new browser session's `FAAAgent` stays in
  memory for the life of the process. The per-session Flask cookie
  isolates one browser tab's question/score from another's *on the same
  machine*, which is a UX convenience for one person using multiple tabs,
  not a security boundary between untrusted users; this interface should
  not be exposed beyond localhost without adding the authentication,
  rate-limiting, and session-management hardening that is explicitly out
  of scope here.
- **Not a substitute for the proctored exam.** The tool is for offline
  practice only; it has no integration with, and is not intended for use
  during, an actual FAA knowledge test session.

## Evaluation

Two layers of quantitative evidence, not just a demo that happens to run.

### Automated tests (`pytest tests/` — 28 tests)

- `test_schema_validator.py` / `test_grounding_checker.py` — unit tests
  against hand-built inputs (valid, malformed, wrong-citation, and
  hallucinated cases) for the two validation layers.
- `test_agent_workflow.py` — end-to-end tests of both flows via
  `llm_client.MockClient` and a stub knowledge base: first-attempt success,
  retry-after-invalid-JSON, exhausting all attempts on bad output, correct
  and incorrect answer submission, the no-active-question error path, and
  the case where LLM-drafted feedback fails grounding and the agent falls
  back to the question's own (already-grounded) explanation. Each asserts
  the exact `confidence_score` / `feedback_confidence_score` /
  `last_attempts_used` values, not just "no error was raised."
- `test_evaluation.py` — a regression test asserting retrieval hit rate is
  100% against the real `docs/` folder (not a stub), so a future doc edit or
  `TOPIC_QUERIES` change that breaks topic routing fails CI, not just a
  manual eyeball.
- `test_webapp.py` — the same reliability contract exercised over HTTP via
  Flask's test client: the full new-question/submit-answer/score round
  trip, two simulated browser sessions proving per-session isolation (each
  gets its own `FAAAgent`), the no-reference-material and
  no-active-question domain errors returning a handled 200 rather than a
  crash, a malformed `choice` value rejected with a 400 before it can burn
  an LLM call, and a genuinely unexpected exception (from a deliberately
  broken knowledge base) returning a 500 via the global error handler
  rather than an unhandled stack trace.

### Quantitative report (`evaluation.py`)

Run `python evaluation.py` to produce `eval_results.json` and
`EVALUATION_RESULTS.md` — a structured, versioned snapshot of two
measurements:

1. **Retrieval evaluation** — for each of the four topics, does
   `retrieve_by_topic()` return chunks from the expected source document?
   No LLM call; fully deterministic; always runs. Current result: **100%
   hit rate** (4/4).
2. **Generation reliability evaluation** — run `new_question()` for every
   topic through the full agent pipeline, recording success, confidence
   score, and attempts used. By default this runs against
   `OFFLINE_FIXTURES` — a fixed, recorded set of LLM responses, so the
   report is reproducible without an API key (`python evaluation.py --live`
   additionally exercises the real Gemini API, one question per topic, if
   `GEMINI_API_KEY` is set). The `weather` fixture is deliberately
   adversarial — its recorded first response fails schema validation, its
   second passes schema but cites an unretrieved document, and only its
   third is accepted — specifically to prove the retry loop and both
   validation layers reject bad output rather than the report being
   trivially "everything passed first try." Current result: **100% success
   rate, 100/100 average confidence on accepted questions**, with `weather`
   correctly taking 3 attempts and every other topic taking 1.

`EVALUATION_RESULTS.md` is committed as the current snapshot; re-run
`evaluation.py` after any change to `docs/`, `retrieval.py`, the prompts, or
`reliability/grounding_checker.py` to refresh it.

## Unexpected Findings During Testing

Building the adversarial fixture for `evaluation.py`'s `weather` topic
surfaced a real gap in the reliability layer, not a hypothetical one.

**What was expected:** a recorded LLM response containing a fabricated
weather rule ("pilots must keep the aircraft under 2 pounds and avoid
flying within 20 minutes of a full moon") would fail the grounding check,
demonstrating that the check catches hallucinated content.

**What actually happened:** it passed, with a grounding confidence score of
100/100 — the fabricated explanation was accepted as if it were fully
supported by the retrieved weather reference text.

**Root cause:** the grounding check's overlap ratio was computed over *all*
matching words, including common English function words ("a", "the", "of",
"and", "must", "within"). A sentence built mostly of such words plus a
handful of incidentally domain-relevant nouns — "aircraft" and "avoid" both
happen to appear in the real retrieved text, in an entirely unrelated
sentence about collision avoidance ("...can see and avoid, other
aircraft...") — accumulated enough raw overlap to clear the 25% threshold,
regardless of whether the *specific claim* being made was true.

**Why this matters:** it's a concrete demonstration that a reliability
check can look correct in every unit test written *for* it (see
`tests/test_grounding_checker.py`, which used hand-picked hallucinated text
that happened to share little vocabulary with the source) while still
failing on adversarial input designed specifically to probe it. Hand-picked
test cases and adversarial test cases can disagree, and only the latter
caught this.

**Fix:** `reliability/grounding_checker.py` now filters common English
function words (a hardcoded `STOPWORDS` set) before computing the overlap
ratio, so the score reflects overlap in *content* words rather than
incidental sentence structure. The evaluation harness's adversarial fixture
was also changed to a mismatched-citation case (a fake source attribution),
since citation matching is deterministic and doesn't share this weakness —
see `evaluation.py`'s `OFFLINE_FIXTURES["weather"]` and the commit that
introduced the fix.

**What this doesn't fix:** as noted in Known Limitations above, a fabricated
claim built entirely from genuinely domain-relevant content words (not just
function words) could still pass. The stopword fix closes the specific gap
that was found; it does not make the grounding check semantic.
