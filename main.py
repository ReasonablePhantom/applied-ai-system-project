"""CLI for the FAA Part 107 exam-prep agent.

Commands:
  new [topic]     Request a new practice question. Topic is one of
                   airspace, weather, operations, certification (default:
                   operations).
  a / b / c / d   Submit an answer to the current question.
  score           Show the running score.
  help            Show this list of commands.
  quit            Exit.
"""

import logging
import sys

from faa_agent import FAAAgent
from llm_client import GeminiClient
from logging_config import setup_logging

logger = logging.getLogger(__name__)

TOPICS = ("airspace", "weather", "operations", "certification")


def print_question(result):
    if "error" in result:
        print(f"\n[error] {result['error']}")
        if result.get("last_errors"):
            for err in result["last_errors"]:
                print(f"  - {err}")
        return
    print(f"\n{result['question']}")
    for key in ("A", "B", "C", "D"):
        print(f"  {key}. {result['choices'][key]}")


def print_feedback(result):
    if "error" in result:
        print(f"\n[error] {result['error']}")
        return
    verdict = "Correct!" if result["correct"] else "Incorrect."
    print(f"\n{verdict} The correct answer is {result['correct_answer']}.")
    print(result["feedback"])
    print(f"Source: {result['citation']}")
    print(f"Score: {result['score']}")


def main():
    setup_logging()

    print("FAA Part 107 Exam Prep Agent")
    print(f"Topics: {', '.join(TOPICS)}")
    print("Type 'help' for commands.\n")

    try:
        agent = FAAAgent(llm_client=GeminiClient())
    except RuntimeError as e:
        logger.error("Startup failed: %s", e)
        print(f"\n[fatal] {e}")
        sys.exit(1)

    while True:
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not command:
            continue

        try:
            parts = command.split(maxsplit=1)
            verb = parts[0].lower()

            if verb in ("quit", "exit"):
                break
            elif verb == "help":
                print(__doc__)
            elif verb == "score":
                print(agent.session.get_score_summary())
            elif verb == "new":
                topic = parts[1].strip().lower() if len(parts) > 1 else "operations"
                print_question(agent.new_question(topic))
            elif verb in ("a", "b", "c", "d"):
                print_feedback(agent.submit_answer(verb))
            else:
                print("Unknown command. Type 'help' for the command list.")
        except Exception:
            # Belt-and-suspenders boundary: FAAAgent's public methods already
            # catch their own errors and return {"error": ...}, so this only
            # fires on a genuinely unexpected bug — log it and keep the CLI
            # alive instead of crashing the whole session over one command.
            logger.exception("Unexpected error handling command: %r", command)
            print("\n[error] Something went wrong handling that command. See logs/agent.log for details.")


if __name__ == "__main__":
    main()
