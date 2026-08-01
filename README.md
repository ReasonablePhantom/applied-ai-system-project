# FAA Part 107 Exam Prep Agent

An agent that generates FAA Part 107 (small drone) knowledge-test practice
questions and grades your answers, grounding every question and every piece
of feedback in a small retrieved reference set rather than the model's raw
recall. See [diagrams/architecture.md](diagrams/architecture.md) for the
data-flow/architecture diagram and [model_card.md](model_card.md) for the
full design writeup, including the reliability layer and known limitations.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set GEMINI_API_KEY to a real Gemini API key
```

## Run

```bash
python main.py
```

Type `help` at the `>` prompt for the command list (`new [topic]`,
`a`/`b`/`c`/`d` to answer, `score`, `quit`). Logs are written to the console
(INFO+) and to `logs/agent.log` (DEBUG+, created on first run).

## Test

No API key is required — the test suite exercises the full agent loop
against `llm_client.MockClient` instead of a live model:

```bash
pytest tests/ -q
```

## Evaluate

Produces a quantitative, structured report (retrieval hit rate + generation
reliability, confidence scores, attempts used) — see
[model_card.md](model_card.md) § Evaluation for what it measures and why.
No API key needed by default (runs against recorded fixture responses):

```bash
python evaluation.py            # writes eval_results.json + EVALUATION_RESULTS.md
python evaluation.py --live     # also exercises the real Gemini API (needs GEMINI_API_KEY)
```

## Project layout

| Path | Role |
|---|---|
| `docs/` | Part 107 reference material (the knowledge base) |
| `retrieval.py` | Chunking + keyword retrieval over `docs/` |
| `llm_client.py` | `GeminiClient` (real) / `MockClient` (for tests) |
| `schema_validator.py` | Structural check on generated questions |
| `reliability/grounding_checker.py` | Checks LLM output is actually grounded in retrieved text; scores confidence 0-100 |
| `faa_agent.py` | Orchestrator: routes `new_question` / `submit_answer`, retries on validation/grounding failure, surfaces confidence scores |
| `session_store.py` | In-memory current question + score |
| `prompts/` | System/user prompt templates |
| `main.py` | CLI entry point |
| `errors.py` | Typed exceptions used internally by the agent |
| `logging_config.py` | Console + file logging setup |
| `evaluation.py` | Quantitative retrieval + generation-reliability evaluation harness |
| `EVALUATION_RESULTS.md` / `eval_results.json` | Latest evaluation snapshot (Markdown table + JSON) |
