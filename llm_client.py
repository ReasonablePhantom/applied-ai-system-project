"""Gemini API wrapper, matching the llm_client pattern used across this course
(see ai110-module4tinker-docubot-starter and ai110-module5tinker-bughound-starter).
"""

import logging
import os

from dotenv import load_dotenv
from google import genai

# Loads .env into the process environment. Without this, python-dotenv
# being in requirements.txt does nothing on its own — os.getenv() only ever
# reads real environment variables, so a correctly-filled-in .env file is
# silently ignored unless something calls load_dotenv() first. Doing it
# here (module import time, before GEMINI_MODEL_NAME / GeminiClient read
# any env vars) means every entry point that imports this module — main.py,
# evaluation.py, tests — gets .env loaded automatically, with no risk of a
# call site forgetting to do it.
load_dotenv()

logger = logging.getLogger(__name__)

# Configurable via env var instead of a hard pin, so a model swap doesn't
# require a code change.
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class MockClient:
    """Offline stand-in for GeminiClient. Returns queued canned responses so
    tests and the reliability loop can be exercised without a live API key."""

    def __init__(self, responses=None):
        self.responses = list(responses) if responses else []

    def complete(self, system_prompt, user_prompt):
        if self.responses:
            return self.responses.pop(0)
        return ""


class GeminiClient:
    """Thin wrapper around google-genai. A single complete() method keeps this
    interchangeable with MockClient and with every other llm_client.py in the
    course."""

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set. "
                "Copy .env.example to .env and set your key."
            )
        self.client = genai.Client(api_key=api_key)
        logger.info("GeminiClient initialized (model=%s)", GEMINI_MODEL_NAME)

    def complete(self, system_prompt, user_prompt):
        prompt = f"{system_prompt}\n\n{user_prompt}"
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME, contents=prompt
            )
            return response.text or ""
        except Exception:
            # Logged here so the failure is visible; still returns "" rather
            # than raising, because callers (faa_agent.FAAAgent) treat an
            # empty completion as one failed attempt in a bounded retry loop,
            # not a fatal error.
            logger.exception("Gemini API call failed")
            return ""
