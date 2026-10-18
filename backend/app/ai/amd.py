"""AMD Radeon Cloud Token Factory's documented shared chat API; no SDK dependency.

https://amd-aim.github.io/radeon-cloud-docs/api/chat-completions/
https://amd-aim.github.io/radeon-cloud-docs/api/models/
Gemini is deliberately never called here, including on failures.
"""
import asyncio
import json
import time
import httpx
from pydantic import BaseModel, ValidationError
from .providers import AIProvider, GenerationError, ProviderResult, SYSTEM


def amd_response_schema(schema: type[BaseModel]) -> dict:
    """Strict OpenAI schema: all object keys required, without JSON defaults.

    Pydantic defaults still apply locally. Array/string constraints and refs are
    preserved; JSON-object-only models receive the same schema as instructions.
    """
    def visit(value):
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        out = {key: ( {name: visit(child) for name, child in item.items()}
                    if key in ("properties", "$defs") else visit(item))
               for key, item in value.items() if key != "default"}
        if out.get("type") == "object":
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}))
        return out
    return visit(schema.model_json_schema())


class AMDProvider(AIProvider):
    name = "amd"

    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client
        self._catalog = None
        self._catalog_until = 0
        self._catalog_lock = asyncio.Lock()

    def configured(self):
        return bool(self.settings.amd_api_key and self.settings.amd_model)

    async def _request(self, method, path, body=None):
        s = self.settings
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=s.ai_timeout_seconds, follow_redirects=False, trust_env=False)
        # Never put a key in the URL, query, prompt or exception message.
        async with self.client.stream(method, s.amd_base_url + path,
                headers={"Authorization": "Bearer " + s.amd_api_key, "Content-Type": "application/json"}, json=body) as response:
            if response.status_code == 429:
                raise GenerationError("provider_quota", "AMD Token Factory's quota is exhausted. Wait before retrying; your draft is safe.", 429, 60)
            if response.status_code in (401, 403):
                raise GenerationError("provider_auth", "AMD Token Factory rejected the backend credential or account access. Your draft is safe.", 503)
            if response.status_code >= 300:
                raise GenerationError("provider_unavailable", "AMD Token Factory rejected the request or is unavailable. Check backend configuration; your draft is safe.", 503)
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > (1048576 if path == "/models" else 262144):
                    raise GenerationError("invalid_output", "AMD Token Factory returned an oversized response. Your draft is unchanged.")
            return json.loads(content)

    async def _model(self):
        async with self._catalog_lock:
            if self._catalog is None or time.monotonic() >= self._catalog_until:
                catalog = await self._request("GET", "/models")
                if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
                    raise ValueError("Invalid model catalog")
                self._catalog = catalog["data"]
                self._catalog_until = time.monotonic() + 300
            model = next((item for item in self._catalog if isinstance(item, dict) and item.get("id") == self.settings.amd_model), None)
            if not model or model.get("free") is not True or model.get("json_output") is not True:
                raise GenerationError("model_unavailable", "The configured AMD model is unavailable, not marked free, or lacks JSON output. No alternative provider was called.", 503)
            return model

    async def structured(self, task, data, schema):
        s = self.settings
        if not self.configured():
            raise GenerationError("not_configured", "AMD Token Factory requires AMD_API_KEY in the backend environment.", 503)
        try:
            async with asyncio.timeout(s.ai_timeout_seconds):
                model = await self._model()
                response_schema = amd_response_schema(schema)
                fmt = {"type": "json_schema", "json_schema": {"name": schema.__name__, "strict": True, "schema": response_schema}} if model.get("structured_outputs") is True else {"type": "json_object"}
                instructions = SYSTEM + "\nReturn only a JSON object matching the requested schema."
                if fmt["type"] == "json_object":
                    instructions += "\nJSON Schema:\n" + json.dumps(response_schema, separators=(",", ":"))
                messages = [{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps({"task": task, "contextual_data": data}, ensure_ascii=False)}]
                # No documented preflight tokenizer API: conservative UTF-8 byte
                # budget plus framing, rather than pretending to count tokens.
                budget = sum(len(m["content"].encode("utf-8")) for m in messages) + len(json.dumps(fmt).encode("utf-8")) + 256
                if budget > s.ai_max_input_tokens or budget + s.ai_max_output_tokens > model.get("context_length", 0):
                    raise GenerationError("context_limit", "The story context exceeds AMD's conservative input budget. Shorten the draft or canon before retrying.", 422)
                response = await self._request("POST", "/chat/completions", {
                    "model": s.amd_model, "messages": messages, "stream": False,
                    "response_format": fmt, "max_tokens": s.ai_max_output_tokens,
                    "temperature": .85 if task == "continue_story" else .3})
                if not isinstance(response, dict):
                    raise ValueError("Invalid completion envelope")
                choice = response["choices"][0]
                if not isinstance(choice, dict):
                    raise ValueError("Invalid completion choice")
                message = choice["message"]
                if not isinstance(message, dict):
                    raise ValueError("Invalid completion message")
                if choice.get("finish_reason") == "length":
                    raise GenerationError("output_limit", "AMD reached the chapter output limit. Your previous draft is safe; try a shorter idea.", 422)
                if message.get("refusal") or choice.get("finish_reason") == "content_filter":
                    raise GenerationError("blocked", "AMD could not return a chapter for this idea. Revise it and try again.", 422)
                if choice.get("finish_reason") != "stop" or not isinstance(message.get("content"), str):
                    raise ValueError("Missing completed text")
                value = schema.model_validate_json(message["content"])
                usage = response["usage"]
                prompt, output = usage["prompt_tokens"], usage["completion_tokens"]
                if type(prompt) is not int or type(output) is not int or min(prompt, output) < 0:
                    raise ValueError("Invalid usage")
                if output > s.ai_max_output_tokens or prompt > s.ai_max_input_tokens:
                    raise GenerationError("output_limit", "AMD reported usage above the configured token limits. Your draft is unchanged.", 422)
                # Record the actual response model; don't invent provider provenance.
                actual_model = response.get("model")
                if not isinstance(actual_model, str) or actual_model != s.amd_model:
                    raise ValueError("Unexpected response model")
                return ProviderResult(value, prompt, output, actual_model)
        except GenerationError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise GenerationError("timeout", "AMD Token Factory took too long. Your saved draft is safe; retry explicitly.", 504) from None
        except httpx.RequestError:
            raise GenerationError("network", "AMD Token Factory could not be reached. Your draft is safe.", 503) from None
        except (ValidationError, ValueError, KeyError, IndexError, TypeError):
            raise GenerationError("invalid_output", "AMD Token Factory returned an incomplete or invalid structured result. Your draft is unchanged.") from None

    async def close(self):
        if self.client:
            await self.client.aclose()
