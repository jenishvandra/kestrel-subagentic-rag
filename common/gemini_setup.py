"""
Shared Gemini setup used across ingestion, subagents, supervisor and the
baseline. Centralising this here means swapping providers again later
(e.g. back to OpenAI, or to another provider) only touches this one file.

Free tier (no credit card required):
  - Chat: Flash-class models (gemini-2.5-flash, gemini-2.5-flash-lite).
    Pro-class models are paid-only, so we don't use them here.
  - Embeddings: gemini-embedding-001.
Get a free API key at https://aistudio.google.com/apikey

Uses the current `google-genai` SDK (the old `google-generativeai`
package is deprecated) for embeddings, and `langchain-google-genai` for
chat models so subagents/supervisor can use LangChain's tool-calling and
structured-output helpers.
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv

import httpx
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

EMBEDDING_MODEL = "gemini-embedding-001"
# IMPORTANT: "Flash" models (gemini-3.6-flash, etc.) have a free-tier cap of
# only ~20 requests/DAY — nowhere near enough for this project. "Flash-Lite"
# models get a much larger free allowance (reported ~500 requests/day as of
# Sept 2026), so we use a lite model for everything. If this exact name 404s
# for your account (Google renames these often), the error message will
# name the correct current model — update both constants below to match.
SUPERVISOR_MODEL = "gemini-flash-lite-latest"
SUBAGENT_MODEL = "gemini-flash-lite-latest"

PERSIST_DIR = str(Path(__file__).resolve().parent.parent / "chroma_db")

_chroma_client = None  # module-level singleton (see get_chroma_client() docstring)


def _api_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "GOOGLE_API_KEY not set. Get a free key at https://aistudio.google.com/apikey "
            "and put it in a .env file at the project root."
        )
    return key


class GeminiEmbeddingFunction(EmbeddingFunction):
    """A Chroma-compatible embedding function backed by the Gemini
    embeddings API. Used identically at ingest time and query time so
    index and query vectors live in the same space."""

    def __init__(self, task_type: str = "RETRIEVAL_DOCUMENT"):
        self.client = genai.Client(api_key=_api_key())
        self.task_type = task_type

    def __call__(self, input: Documents) -> Embeddings:
        # The free tier rate-limits requests; embed one at a time to stay
        # well under RPM limits for a project of this size (~90 chunks).
        # Retry on transient 429s with backoff so a single rate-limit hit
        # doesn't crash the whole ingestion run.
        vectors = []
        for text in input:
            vectors.append(self._embed_one(text))
        return vectors

    def _embed_one(self, text: str, max_attempts: int = 6):
        delay = 5
        for attempt in range(1, max_attempts + 1):
            try:
                result = self.client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(task_type=self.task_type),
                )
                return result.embeddings[0].values
            except genai_errors.ClientError as exc:
                if getattr(exc, "code", None) == 429 and attempt < max_attempts:
                    print(f"  [rate limited on embedding, waiting {delay}s, attempt {attempt}/{max_attempts}]")
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                    continue
                raise
            except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError, ConnectionError) as exc:
                # Network-level drops (e.g. Windows "connection aborted by the
                # software" / antivirus-firewall interference / flaky wifi)
                # rather than an API error — also worth retrying.
                if attempt < max_attempts:
                    print(f"  [network error ({exc.__class__.__name__}), waiting {delay}s, attempt {attempt}/{max_attempts}]")
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                    continue
                raise


def get_embedding_function() -> GeminiEmbeddingFunction:
    return GeminiEmbeddingFunction()


def get_chroma_client() -> chromadb.PersistentClient:
    """One shared PersistentClient for the whole process. Every file that
    touches Chroma (ingestion, subagents, the baseline) should call this
    instead of constructing its own chromadb.PersistentClient(...).
    Opening more than one client handle against the same on-disk
    directory in the same process — e.g. one in build_collections() and
    a fresh one in run_test_searches(), or one per parallel subagent —
    has been observed to trip a "Nothing found on disk" error in
    chromadb's Rust backend on some platforms (the second handle doesn't
    see the first handle's just-written index segment). A single shared
    client avoids that; concurrent *reads* (the .query() calls subagents
    make) from multiple threads against one client are safe."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=PERSIST_DIR)
    return _chroma_client


def get_supervisor_llm(temperature: float = 0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=SUPERVISOR_MODEL, temperature=temperature, google_api_key=_api_key())


def get_subagent_llm(temperature: float = 0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=SUBAGENT_MODEL, temperature=temperature, google_api_key=_api_key())


def with_retry(runnable):
    """Kept for backward compatibility; prefer invoke_with_retry() below,
    which understands the difference between a transient error (worth
    retrying) and a free-tier DAILY quota exhaustion (not worth retrying
    — it won't clear until tomorrow, so retrying just burns minutes)."""
    return runnable.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)


def is_daily_quota_exhausted(exc: Exception) -> bool:
    """True if this looks like Gemini's free-tier DAILY request quota
    (not a per-minute limit or a transient error) — retrying won't help
    until the quota resets, so callers should fail fast instead of
    burning minutes on exponential backoff."""
    msg = str(exc)
    return ("RESOURCE_EXHAUSTED" in msg or "429" in msg) and (
        "PerDay" in msg or "RequestsPerDay" in msg or "GenerateRequestsPerDayPerProjectPerModel" in msg
    )


def invoke_with_retry(runnable, messages, max_attempts: int = 3):
    """Invoke an LLM runnable, retrying transient errors (network drops,
    5xx, per-minute rate limits) with short backoff — but failing FAST,
    with no retry, on a daily-quota-exhausted error, since retrying that
    is guaranteed to fail again and only wastes time (observed: ~200s
    wasted per question when retrying daily-quota 429s with the old
    exponential-backoff retry). Callers (e.g. eval scripts) can catch the
    re-raised exception and check is_daily_quota_exhausted() on it to
    decide whether to stop the whole run early."""
    delay = 3
    for attempt in range(1, max_attempts + 1):
        try:
            return runnable.invoke(messages)
        except Exception as exc:
            if is_daily_quota_exhausted(exc):
                raise  # no point retrying until tomorrow
            if attempt < max_attempts:
                print(f"    [retrying after {exc.__class__.__name__}, waiting {delay}s, attempt {attempt}/{max_attempts}]")
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            raise
