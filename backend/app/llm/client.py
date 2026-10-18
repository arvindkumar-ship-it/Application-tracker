import asyncio
import json
import logging
import time
from pathlib import Path
import anthropic
from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        self.settings = get_settings()

    def configured(self):
        return bool(self.settings.anthropic_api_key and self.settings.llm_model)

    async def _call(self, prompt_name, variables, schema=None, images=None):
        if not self.configured():
            raise ValueError("Anthropic API key and LLM_MODEL must be configured in the local .env")
        prompt = (Path(__file__).parent / "prompts" / f"{prompt_name}.md").read_text(encoding="utf-8")
        content = list(images or []) + [{"type": "text", "text": json.dumps(variables, ensure_ascii=False)}]
        if schema:
            prompt += "\nReturn only a JSON object matching this schema:\n" + json.dumps(schema.model_json_schema())
        messages = [{"role": "user", "content": content}]
        async with anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key, timeout=90, max_retries=2) as client:
            for attempt in range(3):
                started = time.monotonic()
                response = await client.messages.create(model=self.settings.llm_model, temperature=0, max_tokens=8192, system=prompt, messages=messages)
                logger.info("llm prompt=%s model=%s input_tokens=%s output_tokens=%s ms=%d", prompt_name, self.settings.llm_model, response.usage.input_tokens, response.usage.output_tokens, int((time.monotonic()-started)*1000))
                text = "".join(block.text for block in response.content if block.type == "text").strip()
                if schema is None: return text
                try:
                    if text.startswith("```"): text = text.split("\n",1)[1].rsplit("```",1)[0]
                    return schema.model_validate_json(text)
                except ValueError:
                    if attempt == 2: raise ValueError("Model output did not match the required structure after three attempts") from None
                    # Do not echo invalid content, which may contain sensitive data, to logs.
                    messages += [{"role": "assistant", "content": text}, {"role": "user", "content": "Return valid JSON matching the supplied schema. Do not add fields or omit required fields."}]

    async def complete_structured(self, prompt_name, variables, output_schema, images=None):
        return await self._call(prompt_name, variables, output_schema, images)

    async def complete_text(self, prompt_name, variables, images=None):
        return await self._call(prompt_name, variables, images=images)
