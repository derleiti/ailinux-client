"""
Ollama Client
=============

Local LLM integration via Ollama.
Provides free-tier AI chat without server connection.

Usage:
    client = OllamaClient()
    if client.is_available():
        response = await client.chat("Hello!")
"""

import subprocess
import json
import logging
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger("ailinux.ollama")

# Try httpx for async, fallback to requests
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


@dataclass
class OllamaModel:
    """Represents an Ollama model"""
    name: str
    size: int
    modified: str
    digest: str


class OllamaClient:
    """
    Client for Ollama local LLM

    Features:
    - Auto-detect Ollama installation
    - List available models
    - Chat completion
    - Streaming support
    """

    # Recommended models for different use cases
    RECOMMENDED_MODELS = {
        "general": ["llama3.2", "llama3.1", "mistral", "gemma2"],
        "code": ["codellama", "deepseek-coder", "starcoder2"],
        "small": ["llama3.2:1b", "gemma2:2b", "phi3:mini"],
        "fast": ["llama3.2:1b", "phi3:mini", "tinyllama"],
    }

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._available: Optional[bool] = None
        self._models: List[OllamaModel] = []
        self.default_model = "llama3.2"

    def is_available(self) -> bool:
        """Check if Ollama is running"""
        if self._available is not None:
            return self._available

        try:
            # Try API first
            if HAS_REQUESTS:
                resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
                self._available = resp.status_code == 200
            else:
                # Fallback to checking process
                result = subprocess.run(
                    ["pgrep", "-x", "ollama"],
                    capture_output=True
                )
                self._available = result.returncode == 0

            logger.info(f"Ollama available: {self._available}")
            return self._available

        except Exception as e:
            logger.debug(f"Ollama check failed: {e}")
            self._available = False
            return False

    def get_models(self) -> List[OllamaModel]:
        """Get list of installed models"""
        if not self.is_available():
            return []

        try:
            if HAS_REQUESTS:
                resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
                data = resp.json()
            else:
                result = subprocess.run(
                    ["curl", "-s", f"{self.base_url}/api/tags"],
                    capture_output=True, text=True, timeout=5
                )
                data = json.loads(result.stdout)

            self._models = [
                OllamaModel(
                    name=m.get("name", ""),
                    size=m.get("size", 0),
                    modified=m.get("modified_at", ""),
                    digest=m.get("digest", "")
                )
                for m in data.get("models", [])
            ]

            # Set default model to first available
            if self._models and not any(m.name.startswith(self.default_model) for m in self._models):
                self.default_model = self._models[0].name

            return self._models

        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []

    def has_model(self, model: str) -> bool:
        """Check if a specific model is installed"""
        models = self.get_models()
        return any(m.name == model or m.name.startswith(f"{model}:") for m in models)

    def pull_model(self, model: str) -> bool:
        """Pull/download a model"""
        try:
            logger.info(f"Pulling model: {model}")
            result = subprocess.run(
                ["ollama", "pull", model],
                capture_output=True,
                text=True,
                timeout=600  # 10 min timeout
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to pull model: {e}")
            return False

    def chat(
        self,
        message: str,
        model: str = None,
        system_prompt: str = None,
        temperature: float = 0.7,
        context: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Send chat message (synchronous)

        Args:
            message: User message
            model: Model name (default: auto-select)
            system_prompt: System prompt
            temperature: Sampling temperature
            context: Previous messages for context

        Returns:
            {"response": "...", "model": "...", "done": True}
        """
        if not self.is_available():
            return {"error": "Ollama not available"}

        model = model or self.default_model

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }

        try:
            if HAS_REQUESTS:
                resp = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=120
                )
                data = resp.json()
            else:
                result = subprocess.run(
                    ["curl", "-s", "-X", "POST",
                     f"{self.base_url}/api/chat",
                     "-H", "Content-Type: application/json",
                     "-d", json.dumps(payload)],
                    capture_output=True, text=True, timeout=120
                )
                data = json.loads(result.stdout)

            return {
                "response": data.get("message", {}).get("content", ""),
                "model": model,
                "done": data.get("done", True),
                "eval_count": data.get("eval_count", 0),
                "eval_duration": data.get("eval_duration", 0),
            }

        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {"error": str(e)}

    async def chat_async(
        self,
        message: str,
        model: str = None,
        system_prompt: str = None,
        temperature: float = 0.7,
        context: List[Dict] = None
    ) -> Dict[str, Any]:
        """Async chat (requires httpx)"""
        if not HAS_HTTPX:
            # Fallback to sync
            return self.chat(message, model, system_prompt, temperature, context)

        if not self.is_available():
            return {"error": "Ollama not available"}

        model = model or self.default_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature}
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                )
                data = resp.json()

            return {
                "response": data.get("message", {}).get("content", ""),
                "model": model,
                "done": data.get("done", True),
            }

        except Exception as e:
            logger.error(f"Async chat error: {e}")
            return {"error": str(e)}

    async def chat_stream(
        self,
        message: str,
        model: str = None,
        system_prompt: str = None,
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Streaming chat response

        Yields chunks of the response as they arrive.
        """
        if not HAS_HTTPX:
            # Non-streaming fallback
            result = self.chat(message, model, system_prompt, temperature)
            yield result.get("response", result.get("error", ""))
            return

        model = model or self.default_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature}
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                            if data.get("done"):
                                break

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"[Error: {e}]"

    def generate(
        self,
        prompt: str,
        model: str = None,
        system: str = None,
        temperature: float = 0.7
    ) -> str:
        """Simple text generation (non-chat)"""
        if not self.is_available():
            return ""

        model = model or self.default_model

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature}
        }
        if system:
            payload["system"] = system

        try:
            if HAS_REQUESTS:
                resp = requests.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=120
                )
                return resp.json().get("response", "")
            else:
                result = subprocess.run(
                    ["curl", "-s", "-X", "POST",
                     f"{self.base_url}/api/generate",
                     "-H", "Content-Type: application/json",
                     "-d", json.dumps(payload)],
                    capture_output=True, text=True, timeout=120
                )
                return json.loads(result.stdout).get("response", "")

        except Exception as e:
            logger.error(f"Generate error: {e}")
            return ""

    def get_recommended_model(self, category: str = "general") -> Optional[str]:
        """Get first available recommended model for category"""
        models = self.get_models()
        model_names = [m.name for m in models]

        for rec in self.RECOMMENDED_MODELS.get(category, []):
            for m in model_names:
                if m == rec or m.startswith(f"{rec}:"):
                    return m

        return self.default_model if models else None


# Global instance
ollama_client = OllamaClient()
