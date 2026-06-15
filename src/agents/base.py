from abc import ABC, abstractmethod
from typing import Any

import requests

from src.core.config import settings


class BaseAgent(ABC):
    def __init__(self, model_name: str, temperature: float = 0.0):
        self.model_name = model_name
        self.temperature = temperature

    @abstractmethod
    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Exécute l'agent avec les données d'entrée fournies et retourne la réponse."""
        pass

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Appelle le LLM configuré ou lève une exception."""
        model_lower = self.model_name.lower()
        payload: dict[str, Any]

        if "gpt" in model_lower or "openai" in model_lower:
            api_key = settings.OPENAI_API_KEY
            if not api_key:
                raise ValueError("OPENAI_API_KEY non configurée.")
            
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": self.temperature
            }
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])

        elif "claude" in model_lower or "anthropic" in model_lower:
            api_key = settings.ANTHROPIC_API_KEY
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY non configurée.")
            
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": self.model_name,
                "max_tokens": 4000,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": self.temperature
            }
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return str(response.json()["content"][0]["text"])

        elif "gemini" in model_lower or "google" in model_lower:
            api_key = settings.GEMINI_API_KEY
            if not api_key:
                raise ValueError("GEMINI_API_KEY non configurée.")
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={api_key}"
            headers = {
                "Content-Type": "application/json"
            }
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{
                            "text": (
                                f"System Prompt:\n{system_prompt}\n\n"
                                f"User Prompt:\n{user_prompt}"
                            )
                        }]
                    }
                ],
                "generationConfig": {
                    "temperature": self.temperature
                }
            }
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return str(data["candidates"][0]["content"]["parts"][0]["text"])

        else:
            raise ValueError(f"Modèle non supporté ou inconnu : {self.model_name}")
