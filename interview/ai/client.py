import json
import re
from typing import Any

import requests
from django.conf import settings


class AIClientError(RuntimeError):
    """Raised when the external AI provider is unavailable or invalid."""


class HuggingFaceClient:
    def __init__(self, provider=None, token=None, model=None):
        self.provider = (provider or getattr(settings, "AI_PROVIDER", "huggingface")).lower()
        self.token = token or getattr(settings, "HF_TOKEN", "")
        self.model = model or getattr(settings, "AI_MODEL", "Qwen/Qwen2.5-7B-Instruct")

    @property
    def is_configured(self):
        return bool(self.token) and bool(self.model)

    def complete(self, prompt: str, system_prompt: str) -> str:
        if not self.is_configured:
            raise AIClientError("AI provider is not configured. Add HF_TOKEN and AI_MODEL in your environment.")

        url = "https://router.huggingface.co/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 600,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
        except requests.RequestException as exc:
            raise AIClientError("The AI service is temporarily unavailable.") from exc

        if response.status_code in {401, 403}:
            raise AIClientError("The AI token appears to be invalid.")
        if response.status_code == 429:
            raise AIClientError("The AI provider rate limit has been reached.")
        if response.status_code >= 400:
            raise AIClientError(f"The AI provider is unavailable right now (HTTP {response.status_code}).")

        try:
            data = response.json()
        except ValueError as exc:
            raise AIClientError("The AI provider returned an invalid response.") from exc

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AIClientError("The AI provider returned an invalid response.")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise AIClientError("The AI provider returned an invalid response.")

        result = message.get("content", "")
        if not isinstance(result, str) or not result.strip():
            raise AIClientError("The AI provider returned an empty response.")

        return result

    @staticmethod
    def parse_json(raw: str) -> dict[str, Any]:
        if not raw:
            raise AIClientError("The AI provider returned an empty response.")

        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise AIClientError("The AI provider returned malformed JSON.")
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise AIClientError("The AI provider returned malformed JSON.") from exc

        if not isinstance(data, dict):
            raise AIClientError("The AI provider returned malformed JSON.")

        return data
