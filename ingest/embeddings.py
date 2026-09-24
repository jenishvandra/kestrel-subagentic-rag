"""
Shared Gemini embedding function, wrapped so it can be plugged directly
into Chroma's `embedding_function=` parameter.

Uses Google's free-tier Gemini API (https://ai.google.dev) instead of
OpenAI, via LangChain's GoogleGenerativeAIEmbeddings. Chroma expects a
plain callable: `fn(list[str]) -> list[list[float]]`, so we wrap the
LangChain embeddings object in a tiny adapter.
"""

import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings

EMBEDDING_MODEL = "models/text-embedding-004"


class ChromaGeminiEmbeddingFunction:
    """Chroma-compatible wrapper around LangChain's Gemini embeddings."""

    def __init__(self, api_key: str, model: str = EMBEDDING_MODEL):
        self._lc_embeddings = GoogleGenerativeAIEmbeddings(model=model, google_api_key=api_key)

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._lc_embeddings.embed_documents(list(input))

    def name(self) -> str:
        return "gemini-text-embedding-004"


def get_embedding_function() -> ChromaGeminiEmbeddingFunction:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY not set. Put it in a .env file at the project root. "
            "Get a free key at https://aistudio.google.com/apikey"
        )
    return ChromaGeminiEmbeddingFunction(api_key=api_key)
