"""LLM factory: OpenAI and Groq."""

from typing import Literal

from langchain_core.language_models import BaseChatModel

from normalisation_rules.config import OPENAI_API_KEY, GROQ_API_KEY


def get_llm(
    provider: Literal["openai", "groq"] = "openai",
    model: str | None = None,
    temperature: float = 0.2,
) -> BaseChatModel:
    """
    Return a chat model for the given provider.
    - openai: uses OPENAI_API_KEY, default model gpt-4o-mini
    - groq: uses GROQ_API_KEY, default model llama-3.1-8b-instant
    """
    if provider == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "gpt-4o-mini",
            temperature=temperature,
            api_key=OPENAI_API_KEY,
        )
    if provider == "groq":
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set")
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model or "llama-3.1-8b-instant",
            temperature=temperature,
            api_key=GROQ_API_KEY,
        )
    raise ValueError(f"Unknown provider: {provider}. Use 'openai' or 'groq'.")
