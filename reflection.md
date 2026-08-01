# Reflection: Collaborating with AI During Development

> Draft based on this project's actual development conversation with Claude
> Code — the events described below genuinely happened in that order.
> Personalize the commentary and takeaways to your own voice before
> submitting.

This entire system — architecture, code, tests, and evaluation harness —
was built in collaboration with Claude Code, an AI coding assistant, across
one extended session. Two concrete moments stood out.

## A Good Suggestion: Designing the Evaluation Fixture to Be Adversarial

When asked to build a quantitative evaluation harness (`evaluation.py`) to
prove the reliability layer actually works, Claude didn't just write a
script that runs the happy path and reports success. It deliberately
constructed one topic's recorded LLM responses as a multi-step adversarial
sequence: a response that should fail schema validation, followed by one
that should fail the grounding check, followed by a genuinely valid one —
specifically so the report would demonstrate the retry loop and both
validation layers *rejecting* bad output, not just a run where everything
happened to pass on the first try.

This mattered later: that adversarial fixture is exactly what surfaced the
real bug described below. If the evaluation harness had only tested the
happy path, the bug would have shipped silently. The lesson: when building
something meant to prove reliability, design the test to actively try to
break the thing, not just to exercise it.

## A Bad / Wrong Suggestion: The Original Grounding-Checker Design

Claude's first implementation of the grounding checker
(`reliability/grounding_checker.py`) scored "groundedness" as a simple
keyword-overlap ratio between an LLM-generated explanation and the
retrieved reference text — no filtering, just raw word overlap against a
25% threshold. This was proposed and shipped as sufficient for catching
hallucinated content.

It was wrong. When the adversarial fixture above ran a genuinely fabricated
claim ("pilots must keep the aircraft under 2 pounds and avoid flying
within 20 minutes of a full moon") through it, the check scored it 100/100
— fully grounded. The fabricated sentence happened to reuse enough common
English words ("the", "a", "of", "and", "must", "within") plus a couple of
incidentally domain-relevant nouns ("aircraft", "avoid" — both genuinely
present in the real reference text, just in an unrelated sentence about
collision avoidance) to clear the threshold on raw word overlap alone,
regardless of whether the actual claim was true.

This is a meaningful mistake to flag, not a minor one: it was Claude's own
reliability-checking code that had the blind spot, and the existing unit
tests for it (hand-picked hallucinated examples) didn't catch it — only
purpose-built adversarial testing did. It's a reminder that AI-suggested
"safety" or "validation" logic isn't automatically trustworthy just because
it's designed to catch problems; it needs the same adversarial scrutiny as
any other code, and ideally scrutiny from a test case the author didn't
also write with the same blind spot in mind.

## Takeaways

- **Adversarial testing found a bug that code review and ordinary unit
  tests did not.** The fix (filtering common function words before scoring
  overlap — see `model_card.md` § Unexpected Findings During Testing) was
  straightforward once the failure mode was visible, but the failure mode
  itself was not visible from reading the code or from the hand-picked test
  cases already in place.
- **An AI collaborator can propose flawed reliability logic in good faith.**
  The keyword-overlap approach wasn't a lazy shortcut — it was a reasonable
  first attempt at a lightweight grounding signal. It was still wrong in a
  way that mattered, and the way to find that out was to try to break it,
  not to trust that "it sounds like it should work."
- **Trust, but verify — especially the parts meant to keep the system
  honest.** The most important code to adversarially test is the code whose
  entire job is deciding whether other code's output can be trusted.
