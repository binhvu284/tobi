"""
MODEL ROUTER - MMO Agent System
================================
Switch toàn bộ hệ thống sang model khác bằng 1 env variable:
  PRIMARY_MODEL=claude    → dùng Claude Opus (mặc định)
  PRIMARY_MODEL=gpt       → dùng GPT-4o
  PRIMARY_MODEL=gemini    → dùng Gemini Pro
  PRIMARY_MODEL=ollama    → dùng local Ollama (free)
  PRIMARY_MODEL=auto      → tự route thông minh theo task type

Auto routing tiết kiệm ~60% chi phí:
  - "research", "planning"  → Opus (cần phân tích sâu)
  - "writing", "coding"     → Sonnet (cân bằng cost/quality)
  - "simple", "classify"    → Haiku (nhanh, rẻ)
  - "offline"               → Ollama (free)
"""

import os
from abc import ABC, abstractmethod
from typing import Optional


# ─────────────────────────────────────────
# Base Interface
# ─────────────────────────────────────────

class BaseLLMClient(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 2000
    ) -> str:
        pass


# ─────────────────────────────────────────
# Claude (Anthropic)
# ─────────────────────────────────────────

class ClaudeClient(BaseLLMClient):
    def __init__(self, model: str = "claude-opus-4-20250514"):
        try:
            import anthropic
            self.client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
            self.model = model
        except ImportError:
            raise ImportError("Chạy: pip install anthropic")

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        return response.content[0].text


# ─────────────────────────────────────────
# OpenAI (GPT)
# ─────────────────────────────────────────

class OpenAIClient(BaseLLMClient):
    def __init__(self, model: str = "gpt-4o"):
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = model
        except ImportError:
            raise ImportError("Chạy: pip install openai")

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        if system:
            messages = [{"role": "system", "content": system}] + messages

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


# ─────────────────────────────────────────
# Google Gemini
# ─────────────────────────────────────────

class GeminiClient(BaseLLMClient):
    def __init__(self, model: str = "gemini-1.5-pro"):
        try:
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            self._genai = genai
            self.model_name = model
        except ImportError:
            raise ImportError("Chạy: pip install google-generativeai")

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        model = self._genai.GenerativeModel(
            self.model_name,
            system_instruction=system or "",
        )
        # Convert messages → Gemini format
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})

        chat = model.start_chat(history=history)
        response = chat.send_message(messages[-1]["content"])
        return response.text


# ─────────────────────────────────────────
# Ollama (local, free)
# ─────────────────────────────────────────

class OllamaClient(BaseLLMClient):
    def __init__(
        self,
        model: str = None,
        base_url: str = None,
    ):
        import requests
        self._requests = requests
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2")
        self.base_url = base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )

    def complete(self, messages, system=None, max_tokens=2000) -> str:
        if system:
            messages = [{"role": "system", "content": system}] + messages

        resp = self._requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": max_tokens},
            },
            timeout=120,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")
        return resp.json()["message"]["content"]


# ─────────────────────────────────────────
# Smart Router
# ─────────────────────────────────────────

class ModelRouter:
    """
    Một điểm duy nhất để lấy LLM client phù hợp.

    Cách dùng:
        router = ModelRouter()
        client = router.get_client("research")
        text   = client.complete([{"role": "user", "content": "..."}])

    Hoặc shortcut:
        text = llm_complete("Analyze this...", task_type="research")
    """

    # model_key → (provider, model_name)
    MODEL_CONFIGS: dict[str, tuple[str, str]] = {
        "claude-opus":   ("claude",  "claude-opus-4-20250514"),
        "claude-sonnet": ("claude",  "claude-sonnet-4-20250514"),
        "claude-haiku":  ("claude",  "claude-haiku-3-5-20251001"),
        "gpt-4o":        ("openai",  "gpt-4o"),
        "gpt-4o-mini":   ("openai",  "gpt-4o-mini"),
        "gemini-pro":    ("gemini",  "gemini-1.5-pro"),
        "gemini-flash":  ("gemini",  "gemini-1.5-flash"),
        "ollama":        ("ollama",  ""),
    }

    # task_type → model_key (chỉ dùng khi PRIMARY_MODEL=auto)
    TASK_ROUTING: dict[str, str] = {
        "research":    "claude-opus",    # Phân tích sâu → cần mạnh nhất
        "planning":    "claude-opus",    # Business plan → cần reasoning
        "ceo_review":  "claude-opus",    # Strategic → quan trọng nhất
        "writing":     "claude-sonnet",  # Content → cân bằng
        "coding":      "claude-sonnet",  # Code → cân bằng
        "reporting":   "claude-sonnet",  # Report → cân bằng
        "simple":      "claude-haiku",   # Q&A đơn giản → rẻ nhất
        "classify":    "claude-haiku",   # Phân loại → rẻ nhất
        "offline":     "ollama",         # Không cần internet → free
    }

    # Giá ước tính (để log)
    COST_TIER: dict[str, str] = {
        "claude-opus":   "$$$",
        "claude-sonnet": "$$",
        "claude-haiku":  "$",
        "gpt-4o":        "$$$",
        "gpt-4o-mini":   "$",
        "gemini-pro":    "$$",
        "gemini-flash":  "$",
        "ollama":        "Free",
    }

    def _resolve_model_key(self, task_type: str) -> str:
        primary = os.getenv("PRIMARY_MODEL", "claude").lower().strip()

        alias_map = {
            "claude":        "claude-opus",
            "opus":          "claude-opus",
            "claude-opus":   "claude-opus",
            "sonnet":        "claude-sonnet",
            "claude-sonnet": "claude-sonnet",
            "haiku":         "claude-haiku",
            "claude-haiku":  "claude-haiku",
            "gpt":           "gpt-4o",
            "openai":        "gpt-4o",
            "gpt-4o":        "gpt-4o",
            "gpt-mini":      "gpt-4o-mini",
            "gemini":        "gemini-pro",
            "google":        "gemini-pro",
            "gemini-pro":    "gemini-pro",
            "gemini-flash":  "gemini-flash",
            "ollama":        "ollama",
            "local":         "ollama",
        }

        if primary == "auto":
            return self.TASK_ROUTING.get(task_type, "claude-sonnet")

        return alias_map.get(primary, "claude-opus")

    def get_client(self, task_type: str = "research") -> BaseLLMClient:
        model_key = self._resolve_model_key(task_type)
        provider, model_name = self.MODEL_CONFIGS[model_key]

        if provider == "claude":
            return ClaudeClient(model_name)
        elif provider == "openai":
            return OpenAIClient(model_name)
        elif provider == "gemini":
            return GeminiClient(model_name)
        elif provider == "ollama":
            return OllamaClient()
        else:
            # Fallback an toàn
            return ClaudeClient()

    def log_cost(self, task_type: str) -> None:
        key = self._resolve_model_key(task_type)
        tier = self.COST_TIER.get(key, "??")
        print(f"[ModelRouter] task={task_type} | model={key} | cost={tier}")


# ─────────────────────────────────────────
# Singleton + convenience functions
# ─────────────────────────────────────────

_router = ModelRouter()


def get_llm(task_type: str = "research") -> BaseLLMClient:
    """Lấy LLM client phù hợp theo task type."""
    return _router.get_client(task_type)


def llm_complete(
    prompt: str,
    task_type: str = "research",
    system: Optional[str] = None,
    max_tokens: int = 2000,
) -> str:
    """
    One-liner để call LLM với auto routing.

    Ví dụ:
        result = llm_complete("Analyze niche X", task_type="research")
        plan   = llm_complete("Create plan for Y", task_type="planning")
        title  = llm_complete("Write title for Z", task_type="simple")
    """
    client = get_llm(task_type)
    messages = [{"role": "user", "content": prompt}]
    return client.complete(messages, system=system, max_tokens=max_tokens)


# ─────────────────────────────────────────
# Quick test
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("=== Model Router Test ===")
    print(f"PRIMARY_MODEL = {os.getenv('PRIMARY_MODEL', 'claude (default)')}")
    print()

    for task in ["research", "writing", "simple", "offline"]:
        key = _router._resolve_model_key(task)
        tier = _router.COST_TIER.get(key, "??")
        print(f"  {task:<12} → {key:<16} ({tier})")
