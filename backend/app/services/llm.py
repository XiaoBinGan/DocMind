import os
from typing import List, Optional
from app.core.config import settings

class LLMService:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            if self.provider == "openai":
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            elif self.provider == "anthropic":
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            elif self.provider in ("local", "ollama"):
                from openai import AsyncOpenAI
                # Ollama 默认地址 http://localhost:11434
                base_url = settings.LOCAL_MODEL_URL
                self._client = AsyncOpenAI(
                    base_url=base_url,
                    api_key="not-needed"
                )
        return self._client
    
    def get_model(self) -> str:
        if self.provider == "openai":
            return settings.OPENAI_MODEL
        elif self.provider == "anthropic":
            return settings.ANTHROPIC_MODEL
        elif self.provider in ("local", "ollama"):
            return settings.LOCAL_MODEL_NAME
    
    async def generate(
        self, 
        system_prompt: str, 
        user_prompt: str,
        stream: bool = True
    ):
        """Generate a response from the LLM."""
        if self.provider == "anthropic":
            async with self.client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            ) as stream_response:
                async for text in stream_response.text_stream:
                    yield text
        else:
            model = self.get_model()
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=stream,
                temperature=0.7
            )
            
            if stream:
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        # 过滤掉 <think>...</think> 思考过程
                        if "<think>" in content:
                            continue
                        if "</think>" in content:
                            continue
                        # 如果内容包含 think 标签，尝试提取标签外的内容
                        import re
                        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                        if content.strip():
                            yield content
            else:
                yield response.choices[0].message.content
    
    async def generate_structure(self, prompt: str) -> str:
        """Generate structured output for indexing."""
        system = """You are a document analysis expert. Your task is to analyze document content and produce structured output.
Always respond with valid JSON in the specified format. Do not include any other text."""
        
        response = await self.generate(system, prompt, stream=False)
        # 过滤掉 <think>...</think> 思考过程
        import re
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        return response.strip()

llm_service = LLMService()
