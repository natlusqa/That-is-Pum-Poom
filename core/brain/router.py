"""
KORGAN AI — LLM Router
Intelligent routing between local and cloud LLM providers.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("korgan.router")


class LLMProvider(str, Enum):
    OLLAMA_PRIMARY = "ollama_primary"
    OLLAMA_CODE = "ollama_code"
    CLAUDE = "claude"
    OPENAI = "openai"


class LLMResponse(BaseModel):
    """Response from an LLM provider."""
    content: str
    model: str
    provider: LLMProvider
    tokens_used: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    cached: bool = False


class RoutingDecision(BaseModel):
    """Decision made by the router."""
    provider: LLMProvider
    reason: str
    fallback: Optional[LLMProvider] = None


class LLMRouter:
    """
    Intelligent LLM router that selects the optimal model
    based on task type, complexity, cost, and availability.
    
    Routing Strategy:
    - Simple/short → Local Ollama (Mistral 7B)
    - Code tasks → Local Ollama (DeepSeek Coder)
    - Complex reasoning → Cloud (Claude)
    - Critical/autonomy → Cloud + Local verification
    - Fallback chain: preferred → alternative → cloud
    
    VRAM Management:
    - Monitors GPU memory usage
    - Switches to cloud if VRAM constrained
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._ollama_client = None
        self._claude_client = None
        self._openai_client = None
        self._cost_tracker = CostTracker(
            daily_limit=config.get("global", {}).get("max_api_cost_daily_usd", 5.0)
        )

    async def initialize(self) -> None:
        """Initialize LLM provider connections."""
        local_config = self.config.get("llm", {}).get("local", {})
        cloud_config = self.config.get("llm", {}).get("cloud", {})

        # Initialize Ollama
        try:
            import ollama
            self._ollama_client = ollama.AsyncClient(
                host=local_config.get("host", "http://ollama:11434")
            )
            logger.info("ollama_initialized")
        except Exception as e:
            logger.warning("ollama_init_failed", error=str(e))

        # Initialize Claude
        if cloud_config.get("enabled"):
            try:
                import anthropic
                self._claude_client = anthropic.AsyncAnthropic()
                logger.info("claude_initialized")
            except Exception as e:
                logger.warning("claude_init_failed", error=str(e))

            try:
                import openai
                self._openai_client = openai.AsyncOpenAI()
                logger.info("openai_initialized")
            except Exception as e:
                logger.warning("openai_init_failed", error=str(e))

    def route(
        self,
        task_type: str,
        content_length: int = 0,
        force_cloud: bool = False,
        force_local: bool = False,
    ) -> RoutingDecision:
        """
        Determine which LLM provider to use.
        
        Decision matrix:
        - force_cloud=True → Claude (with OpenAI fallback)
        - force_local=True → Ollama Primary (with Code fallback)
        - task_type=code → Ollama Code
        - task_type=strategic → Claude
        - content_length > threshold → Claude
        - default → Ollama Primary
        """
        cloud_config = self.config.get("llm", {}).get("cloud", {})
        routing = cloud_config.get("routing", {})
        context_threshold = routing.get("context_length_threshold", 4000)
        cloud_enabled = cloud_config.get("enabled", False)

        if force_cloud and cloud_enabled:
            return RoutingDecision(
                provider=LLMProvider.CLAUDE,
                reason="Принудительное использование cloud",
                fallback=LLMProvider.OPENAI,
            )

        if force_local:
            return RoutingDecision(
                provider=LLMProvider.OLLAMA_PRIMARY,
                reason="Принудительное использование local",
                fallback=LLMProvider.OLLAMA_CODE,
            )

        # Code tasks
        if task_type in ("code_analysis", "code_generation", "code_review", "code_task"):
            return RoutingDecision(
                provider=LLMProvider.OLLAMA_CODE,
                reason="Задача на код → DeepSeek Coder",
                fallback=LLMProvider.CLAUDE if cloud_enabled else LLMProvider.OLLAMA_PRIMARY,
            )

        # Strategic / complex
        if task_type in ("strategic", "complex_reasoning") and cloud_enabled:
            return RoutingDecision(
                provider=LLMProvider.CLAUDE,
                reason="Стратегический анализ → Claude",
                fallback=LLMProvider.OLLAMA_PRIMARY,
            )

        # Long context
        if content_length > context_threshold and cloud_enabled:
            return RoutingDecision(
                provider=LLMProvider.CLAUDE,
                reason=f"Длинный контекст ({content_length} > {context_threshold}) → Claude",
                fallback=LLMProvider.OLLAMA_PRIMARY,
            )

        # Cost check
        if self._cost_tracker.is_over_limit():
            return RoutingDecision(
                provider=LLMProvider.OLLAMA_PRIMARY,
                reason="Лимит API расходов → Local only",
                fallback=LLMProvider.OLLAMA_CODE,
            )

        # Default
        return RoutingDecision(
            provider=LLMProvider.OLLAMA_PRIMARY,
            reason="Стандартная задача → Local Mistral",
            fallback=LLMProvider.OLLAMA_CODE,
        )

    async def generate(
        self,
        prompt: str,
        task_type: str = "conversation",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        force_cloud: bool = False,
        force_local: bool = False,
    ) -> LLMResponse:
        """
        Generate a response using the best available LLM.
        Includes automatic fallback on failure.
        """
        decision = self.route(
            task_type=task_type,
            content_length=len(prompt),
            force_cloud=force_cloud,
            force_local=force_local,
        )

        logger.info(
            "llm_routing",
            provider=decision.provider.value,
            reason=decision.reason,
            task_type=task_type,
        )

        try:
            return await self._call_provider(
                provider=decision.provider,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning(
                "llm_primary_failed",
                provider=decision.provider.value,
                error=str(e),
            )
            if decision.fallback:
                logger.info("llm_fallback", fallback=decision.fallback.value)
                return await self._call_provider(
                    provider=decision.fallback,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            raise

    async def _call_provider(
        self,
        provider: LLMProvider,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call a specific LLM provider."""
        start = time.monotonic()

        if provider in (LLMProvider.OLLAMA_PRIMARY, LLMProvider.OLLAMA_CODE):
            return await self._call_ollama(provider, prompt, temperature, max_tokens, start)
        elif provider == LLMProvider.CLAUDE:
            return await self._call_claude(prompt, temperature, max_tokens, start)
        elif provider == LLMProvider.OPENAI:
            return await self._call_openai(prompt, temperature, max_tokens, start)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def _call_ollama(
        self,
        provider: LLMProvider,
        prompt: str,
        temperature: float,
        max_tokens: int,
        start: float,
    ) -> LLMResponse:
        """Call Ollama local LLM."""
        if not self._ollama_client:
            raise RuntimeError("Ollama client not initialized")

        models = self.config.get("llm", {}).get("local", {}).get("models", {})
        model_key = "primary" if provider == LLMProvider.OLLAMA_PRIMARY else "code"
        model_name = models.get(model_key, {}).get("name", "mistral:7b")

        response = await self._ollama_client.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        )

        latency = int((time.monotonic() - start) * 1000)
        content = response["message"]["content"]

        return LLMResponse(
            content=content,
            model=model_name,
            provider=provider,
            tokens_used=response.get("eval_count", 0),
            latency_ms=latency,
            cost_usd=0.0,
        )

    async def _call_claude(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        start: float,
    ) -> LLMResponse:
        """Call Claude API."""
        if not self._claude_client:
            raise RuntimeError("Claude client not initialized")

        model = (
            self.config.get("llm", {})
            .get("cloud", {})
            .get("providers", {})
            .get("claude", {})
            .get("model", "claude-sonnet-4-20250514")
        )

        response = await self._claude_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        latency = int((time.monotonic() - start) * 1000)
        content = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

        # Estimate cost (Claude Sonnet pricing approximate)
        cost = (response.usage.input_tokens * 3.0 + response.usage.output_tokens * 15.0) / 1_000_000
        self._cost_tracker.add(cost)

        return LLMResponse(
            content=content,
            model=model,
            provider=LLMProvider.CLAUDE,
            tokens_used=tokens,
            latency_ms=latency,
            cost_usd=cost,
        )

    async def _call_openai(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        start: float,
    ) -> LLMResponse:
        """Call OpenAI API."""
        if not self._openai_client:
            raise RuntimeError("OpenAI client not initialized")

        model = (
            self.config.get("llm", {})
            .get("cloud", {})
            .get("providers", {})
            .get("openai", {})
            .get("model", "gpt-4o")
        )

        response = await self._openai_client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        latency = int((time.monotonic() - start) * 1000)
        content = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0

        cost = (tokens * 5.0) / 1_000_000  # approximate
        self._cost_tracker.add(cost)

        return LLMResponse(
            content=content,
            model=model,
            provider=LLMProvider.OPENAI,
            tokens_used=tokens,
            latency_ms=latency,
            cost_usd=cost,
        )


class CostTracker:
    """Tracks daily API costs and enforces limits."""

    def __init__(self, daily_limit: float = 5.0):
        self.daily_limit = daily_limit
        self._today_cost: float = 0.0
        self._today_date: str = ""

    def add(self, cost: float) -> None:
        """Add cost to today's total."""
        from datetime import date
        today = date.today().isoformat()
        if today != self._today_date:
            self._today_date = today
            self._today_cost = 0.0
        self._today_cost += cost
        logger.info("cost_tracked", today_total=self._today_cost, added=cost)

    def is_over_limit(self) -> bool:
        """Check if daily limit is exceeded."""
        return self._today_cost >= self.daily_limit

    def get_remaining(self) -> float:
        """Get remaining budget for today."""
        return max(0, self.daily_limit - self._today_cost)

    def get_today_cost(self) -> float:
        """Get today's total cost."""
        return self._today_cost
