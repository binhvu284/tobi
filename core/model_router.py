"""
MODEL ROUTER - Tobi Agent
PRIMARY_MODEL options: openrouter | claude | auto
"""
import os
from abc import ABC, abstractmethod
from typing import Optional
from core.env_utils import safe_load_dotenv
safe_load_dotenv()


class BaseLLMClient(ABC):
    @abstractmethod
    def complete(self, messages: list, system: str = None, max_tokens: int = 2000) -> str:
        pass


class OpenRouterClient(BaseLLMClient):
    # Models verified working (May 2026)
    FREE_MODELS = {
        "research":  "nvidia/nemotron-3-super-120b-a12b:free",
        "planning":  "nvidia/nemotron-3-super-120b-a12b:free",
        "ceo_review":"nvidia/nemotron-3-super-120b-a12b:free",
        "writing":   "nvidia/nemotron-3-super-120b-a12b:free",
        "coding":    "nvidia/nemotron-3-super-120b-a12b:free",
        "reporting": "nvidia/nemotron-3-super-120b-a12b:free",
        "simple":    "nvidia/nemotron-3-super-120b-a12b:free",
        "classify":  "nvidia/nemotron-3-super-120b-a12b:free",
        "default":   "nvidia/nemotron-3-super-120b-a12b:free",
    }
    FALLBACK_MODELS = {
        "default": "google/gemma-4-31b-it:free",
    }

    def __init__(self, model: str = None, task_type: str = "default"):
        from openai import OpenAI
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY missing in .env")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model or self.FREE_MODELS.get(task_type, self.FREE_MODELS["default"])

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        if system:
            messages = [{"role": "system", "content": system}] + messages
        headers = {
            "HTTP-Referer": "https://github.com/binhvu284/tobi",
            "X-Title": "Tobi Agent",
        }
        try:
            r = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                extra_headers=headers,
            )
            return r.choices[0].message.content
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                fallback = self.FALLBACK_MODELS["default"]
                r = self.client.chat.completions.create(
                    model=fallback,
                    messages=messages,
                    max_tokens=max_tokens,
                    extra_headers=headers,
                )
                return r.choices[0].message.content
            raise


class ClaudeClient(BaseLLMClient):
    def __init__(self, model: str = "claude-opus-4-20250514"):
        import anthropic
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = model

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        r = self.client.messages.create(**kwargs)
        return r.content[0].text


class ModelRouter:
    def get_client(self, task_type: str = "default") -> BaseLLMClient:
        primary = os.getenv("PRIMARY_MODEL", "openrouter").lower().strip()

        if primary == "openrouter":
            return OpenRouterClient(task_type=task_type)
        elif primary in ("claude", "opus"):
            return ClaudeClient("claude-opus-4-20250514")
        elif primary in ("sonnet", "claude-sonnet"):
            return ClaudeClient("claude-sonnet-4-20250514")
        elif primary in ("haiku", "claude-haiku"):
            return ClaudeClient("claude-haiku-3-5-20251001")
        elif primary == "auto":
            # Dùng Claude nếu có key, fallback OpenRouter nếu không
            if os.getenv("ANTHROPIC_API_KEY"):
                model_map = {
                    "research": "claude-opus-4-20250514",
                    "planning": "claude-opus-4-20250514",
                    "ceo_review": "claude-opus-4-20250514",
                    "writing": "claude-sonnet-4-20250514",
                    "coding": "claude-sonnet-4-20250514",
                    "simple": "claude-haiku-3-5-20251001",
                }
                model = model_map.get(task_type, "claude-sonnet-4-20250514")
                try:
                    return ClaudeClient(model)
                except Exception:
                    pass
            return OpenRouterClient(task_type=task_type)
        else:
            return OpenRouterClient(task_type=task_type)


_router = ModelRouter()


def get_llm(task_type: str = "default") -> BaseLLMClient:
    return _router.get_client(task_type)


def llm_complete(prompt: str, task_type: str = "default",
                 system: Optional[str] = None, max_tokens: int = 2000) -> str:
    client = get_llm(task_type)
    return client.complete([{"role": "user", "content": prompt}],
                           system=system, max_tokens=max_tokens)


if __name__ == "__main__":
    print("=== Tobi Model Router ===")
    print(f"PRIMARY_MODEL: {os.getenv('PRIMARY_MODEL', 'openrouter')}")
    result = llm_complete("Say: Tobi is online", task_type="simple")
    print(f"Test response: {result}")
