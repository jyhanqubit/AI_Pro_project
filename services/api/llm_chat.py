"""Minimal, degrading LLM chat helper for the operator copilot. CLAUDE.md §8, §12, §22.

This is the *answering* counterpart to the extraction providers: given a system prompt and a user
message, it returns the model's text. It is opt-in exactly like the extraction providers —
``LLM_PROVIDER=openai`` (GPT-4o) or ``anthropic`` (Claude) plus a key. With ``mock`` (default) or
a missing SDK/key it reports itself unavailable so the copilot falls back to the deterministic,
rule-based answer. It never fabricates: on any error the caller degrades, it does not invent text.

Only the operator's question and the already-assembled, as-of grounded context are sent to the
provider — never secrets, personal data, or a full licensed article body.
"""

from __future__ import annotations

from config.settings import get_settings


class LlmChatUnavailable(RuntimeError):
    """Raised when no chat provider is configured/installed (caller degrades to rule-based)."""


def chat_provider() -> str:
    """The configured provider name for chat: ``openai`` | ``anthropic`` | ``mock``."""
    return get_settings().llm_provider.strip().lower()


def chat_available() -> bool:
    """True only if a real provider is selected AND its SDK imports (key checked lazily at call)."""
    provider = chat_provider()
    if provider == "openai":
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        s = get_settings()
        return bool(s.openai_api_key) or _env_has("OPENAI_API_KEY")
    if provider == "anthropic":
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        s = get_settings()
        return bool(s.llm_api_key) or _env_has("ANTHROPIC_API_KEY")
    return False


def _env_has(name: str) -> bool:
    import os

    return bool(os.environ.get(name))


def chat(system: str, user: str, *, max_tokens: int = 700) -> str:
    """Return the model's text for (system, user). Raises ``LlmChatUnavailable`` if not configured.

    Deterministic-as-possible (temperature 0). A ``_client`` may be injected on this module for
    tests (see ``set_test_client``) to exercise the assembly without a network or key.
    """
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT(system, user)

    provider = chat_provider()
    if provider == "openai":
        return _openai_chat(system, user, max_tokens)
    if provider == "anthropic":
        return _anthropic_chat(system, user, max_tokens)
    raise LlmChatUnavailable(f"no chat provider configured (LLM_PROVIDER={provider!r})")


def _openai_chat(system: str, user: str, max_tokens: int) -> str:
    try:
        import openai
    except ImportError as exc:
        raise LlmChatUnavailable("the 'openai' package is not installed") from exc
    s = get_settings()
    client = openai.OpenAI(api_key=s.openai_api_key) if s.openai_api_key else openai.OpenAI()
    resp = client.chat.completions.create(
        model=s.openai_model,
        temperature=0,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip()


def _anthropic_chat(system: str, user: str, max_tokens: int) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise LlmChatUnavailable("the 'anthropic' package is not installed") from exc
    s = get_settings()
    client = anthropic.Anthropic(api_key=s.llm_api_key) if s.llm_api_key else anthropic.Anthropic()
    resp = client.messages.create(
        model=s.llm_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


# --- test injection (no network) -----------------------------------------------------------------
_TEST_CLIENT = None


def set_test_client(fn) -> None:
    """Inject a ``(system, user) -> str`` callable for tests; pass ``None`` to clear."""
    global _TEST_CLIENT
    _TEST_CLIENT = fn
