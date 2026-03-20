"""
KORGAN AI — Central Orchestrator
The main brain that coordinates all system components.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

from core.brain.reasoning import ReasoningEngine, ReasoningLog
from core.brain.router import LLMRouter, LLMResponse
from core.memory.manager import MemoryManager
from core.security.permissions import PermissionManager
from core.autonomy.engine import AutonomyEngine

logger = structlog.get_logger("korgan.orchestrator")


class IntentType(str, Enum):
    """Classified intent types for incoming requests."""
    CONVERSATION = "conversation"
    CODE_TASK = "code_task"
    GIT_OPERATION = "git_operation"
    SYSTEM_COMMAND = "system_command"
    SYSTEM_QUERY = "system_query"
    PROJECT_ANALYSIS = "project_analysis"
    STRATEGIC = "strategic"
    MEMORY_QUERY = "memory_query"
    AUTONOMY_CHANGE = "autonomy_change"
    STATUS_QUERY = "status_query"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OrchestratorRequest(BaseModel):
    """Incoming request to the orchestrator."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    interface: str = "api"  # telegram, desktop, voice, api
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrchestratorResponse(BaseModel):
    """Response from the orchestrator."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    content: str
    reasoning: Optional[str] = None
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    suggested_actions: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Orchestrator:
    """
    Central orchestrator — the brain of KORGAN AI.
    
    Responsibilities:
    - Receive input from all interfaces
    - Classify intent
    - Build execution plan
    - Coordinate agents
    - Manage reasoning chain
    - Return structured response
    """

    def __init__(
        self,
        llm_router: LLMRouter,
        reasoning_engine: ReasoningEngine,
        memory_manager: MemoryManager,
        permission_manager: PermissionManager,
        autonomy_engine: AutonomyEngine,
        agents: dict[str, Any] | None = None,
        feedback_loop: Any = None,
        crisis_detector: Any = None,
    ):
        self.llm = llm_router
        self.reasoning = reasoning_engine
        self.memory = memory_manager
        self.permissions = permission_manager
        self.autonomy = autonomy_engine
        self.agents = agents or {}
        self.feedback = feedback_loop
        self.crisis = crisis_detector
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the core system prompt for KORGAN AI."""
        return """Ты — KORGAN, персональная AI-операционная система, созданная Мистером Корганом (Amanat Korgan).

Твои принципы:
- Ты стратегичен и лаконичен
- Ты спокоен и уверен
- Ты не болтлив — каждое слово имеет вес
- Ты объясняешь свои решения кратко
- Ты предлагаешь улучшения, когда видишь возможность
- Ты ведёшь лог своего reasoning
- Ты НИКОГДА не действуешь вне разрешённых правил
- Ты обращаешься к создателю "Мистер Корган" с уважением

Ты управляешь:
- Разработкой (код, Git, проекты)
- Системой ПК (мониторинг, команды)
- Памятью (долговременная, оперативная, семантическая)
- Безопасностью (sandbox, разрешения, аудит)

Текущий уровень автономности определяется конфигурацией.
Всегда проверяй разрешения перед выполнением действий."""

    async def process(self, request: OrchestratorRequest) -> OrchestratorResponse:
        """
        Main entry point — process an incoming request.
        
        Pipeline:
        1. Classify intent
        2. Retrieve relevant memory
        3. Build context
        4. Route to appropriate handler
        5. Execute plan (with permission checks)
        6. Store in memory
        7. Return response
        """
        log = logger.bind(request_id=request.id, interface=request.interface)
        log.info("processing_request", content_preview=request.content[:100])

        # Step 1: Start reasoning chain
        reasoning_log = self.reasoning.start_chain(request.id)

        try:
            # Step 2: Classify intent
            intent = await self._classify_intent(request, reasoning_log)
            log.info("intent_classified", intent=intent.value)

            # Step 3: Retrieve relevant memory
            memory_context = await self._retrieve_memory(request, reasoning_log)

            # Step 4: Build full context
            context = self._build_context(request, intent, memory_context)

            # Step 5: Route and execute
            if intent in (IntentType.GIT_OPERATION, IntentType.SYSTEM_COMMAND):
                response = await self._handle_agent_task(
                    request, intent, context, reasoning_log
                )
            elif intent == IntentType.STRATEGIC:
                response = await self._handle_strategic(
                    request, context, reasoning_log
                )
            elif intent == IntentType.AUTONOMY_CHANGE:
                response = await self._handle_autonomy_change(
                    request, context, reasoning_log
                )
            else:
                response = await self._handle_conversation(
                    request, context, reasoning_log
                )

            # Step 6: Store in memory
            await self._store_in_memory(request, response)

            # Step 7: Finalize reasoning
            self.reasoning.complete_chain(reasoning_log)

            return response

        except Exception as e:
            log.error("orchestrator_error", error=str(e))
            self.reasoning.add_step(
                reasoning_log, "error", f"Ошибка обработки: {str(e)}"
            )
            return OrchestratorResponse(
                request_id=request.id,
                content=f"Произошла ошибка при обработке запроса. {str(e)}",
                reasoning=reasoning_log.to_text(),
                metadata={"error": True, "error_type": type(e).__name__},
            )

    async def _classify_intent(
        self, request: OrchestratorRequest, reasoning_log: ReasoningLog
    ) -> IntentType:
        """Classify the user's intent using LLM."""
        self.reasoning.add_step(reasoning_log, "classify", "Определяю намерение...")

        classification_prompt = f"""Classify the following user message into one of these categories.
Return ONLY the category name, nothing else.

Categories: conversation, code_task, git_operation, system_command, system_query, 
project_analysis, strategic, memory_query, autonomy_change, status_query

Message: {request.content}"""

        result = await self.llm.generate(
            prompt=classification_prompt,
            task_type="classification",
            max_tokens=20,
            temperature=0.1,
        )

        # Parse intent
        intent_text = result.content.strip().lower().replace(" ", "_")
        try:
            intent = IntentType(intent_text)
        except ValueError:
            intent = IntentType.CONVERSATION

        self.reasoning.add_step(
            reasoning_log, "classified", f"Намерение: {intent.value}"
        )
        return intent

    async def _retrieve_memory(
        self, request: OrchestratorRequest, reasoning_log: ReasoningLog
    ) -> dict[str, Any]:
        """Retrieve relevant context from memory system."""
        self.reasoning.add_step(reasoning_log, "memory", "Поиск в памяти...")

        context = {}

        # Get relevant facts
        facts = await self.memory.search_facts(request.content, limit=5)
        if facts:
            context["facts"] = facts

        # Get recent conversation history
        history = await self.memory.get_recent_messages(limit=10)
        if history:
            context["history"] = history

        # Semantic search in vector store
        similar = await self.memory.semantic_search(request.content, limit=3)
        if similar:
            context["similar_context"] = similar

        self.reasoning.add_step(
            reasoning_log,
            "memory_retrieved",
            f"Найдено: {len(facts)} фактов, {len(history)} сообщений, {len(similar)} похожих контекстов",
        )
        return context

    def _build_context(
        self,
        request: OrchestratorRequest,
        intent: IntentType,
        memory_context: dict[str, Any],
    ) -> str:
        """Build the full context string for LLM."""
        parts = [self._system_prompt]

        # Add memory context
        if memory_context.get("facts"):
            facts_text = "\n".join(
                f"- {f['key']}: {f['value']}" for f in memory_context["facts"]
            )
            parts.append(f"\nИзвестные факты:\n{facts_text}")

        if memory_context.get("history"):
            history_text = "\n".join(
                f"[{m['role']}]: {m['content'][:200]}"
                for m in memory_context["history"]
            )
            parts.append(f"\nНедавняя история:\n{history_text}")

        # Add intent-specific context
        parts.append(f"\nТекущий запрос ({intent.value}): {request.content}")
        parts.append(f"Интерфейс: {request.interface}")
        parts.append(
            f"Уровень автономности: {self.autonomy.current_level.name}"
        )

        return "\n".join(parts)

    async def _handle_conversation(
        self,
        request: OrchestratorRequest,
        context: str,
        reasoning_log: ReasoningLog,
    ) -> OrchestratorResponse:
        """Handle general conversation requests."""
        self.reasoning.add_step(reasoning_log, "generate", "Генерирую ответ...")

        result = await self.llm.generate(
            prompt=context,
            task_type="conversation",
            temperature=0.7,
        )

        return OrchestratorResponse(
            request_id=request.id,
            content=result.content,
            reasoning=reasoning_log.to_text(),
            metadata={
                "model": result.model,
                "tokens": result.tokens_used,
                "intent": "conversation",
            },
        )

    async def _handle_agent_task(
        self,
        request: OrchestratorRequest,
        intent: IntentType,
        context: str,
        reasoning_log: ReasoningLog,
    ) -> OrchestratorResponse:
        """Handle tasks that require agent execution."""
        self.reasoning.add_step(
            reasoning_log, "agent_task", f"Задача для агента: {intent.value}"
        )

        # Determine which agent to use
        agent_name = self._intent_to_agent(intent)
        agent = self.agents.get(agent_name)

        if not agent:
            return OrchestratorResponse(
                request_id=request.id,
                content=f"Агент '{agent_name}' не доступен.",
                reasoning=reasoning_log.to_text(),
                metadata={"error": True},
            )

        # Check permissions
        permission_check = self.permissions.check_agent_action(
            agent_name=agent_name,
            action=request.content,
        )

        if not permission_check.allowed:
            self.reasoning.add_step(
                reasoning_log,
                "permission_denied",
                f"Действие запрещено: {permission_check.reason}",
            )
            return OrchestratorResponse(
                request_id=request.id,
                content=f"Мистер Корган, это действие требует дополнительного разрешения: {permission_check.reason}",
                reasoning=reasoning_log.to_text(),
                metadata={"permission_denied": True},
            )

        # Check autonomy level
        autonomy_decision = self.autonomy.can_auto_execute(
            agent_name=agent_name,
            action_type=permission_check.action_type,
            risk_level=permission_check.risk_level,
        )

        if autonomy_decision.needs_approval:
            self.reasoning.add_step(
                reasoning_log,
                "needs_approval",
                "Требуется подтверждение от Мистера Коргана",
            )
            # Generate plan preview
            plan = await agent.plan(request.content, context)
            return OrchestratorResponse(
                request_id=request.id,
                content=f"Мистер Корган, предлагаю следующий план:\n\n{plan.description}\n\nПодтвердить выполнение?",
                reasoning=reasoning_log.to_text(),
                suggested_actions=[plan.to_dict()],
                metadata={
                    "awaiting_approval": True,
                    "agent": agent_name,
                    "plan_id": plan.id,
                },
            )

        # Execute
        self.reasoning.add_step(reasoning_log, "executing", "Выполняю...")
        result = await agent.execute_with_tracking(request.content, context)

        # Feed result into feedback loop
        if self.feedback:
            await self.feedback.record_from_action_result(
                agent_name=agent_name,
                action_type=result.action_type,
                task=request.content,
                result=result,
                was_auto=not autonomy_decision.needs_approval,
            )

        # Track errors for crisis detection
        if self.crisis:
            if result.success:
                self.crisis.record_success()
            else:
                self.crisis.record_error()

        return OrchestratorResponse(
            request_id=request.id,
            content=result.summary,
            reasoning=reasoning_log.to_text(),
            actions_taken=[result.to_dict()],
            metadata={
                "agent": agent_name,
                "success": result.success,
            },
        )

    async def _handle_strategic(
        self,
        request: OrchestratorRequest,
        context: str,
        reasoning_log: ReasoningLog,
    ) -> OrchestratorResponse:
        """Handle strategic analysis requests — uses cloud LLM."""
        self.reasoning.add_step(
            reasoning_log, "strategic", "Активирую стратегический режим (Cloud LLM)"
        )

        strategic_prompt = f"""{context}

Это стратегический запрос. Проведи глубокий анализ:
1. Сформулируй минимум 3 альтернативных подхода
2. Оцени trade-offs каждого
3. Дай обоснованную рекомендацию
4. Укажи риски

Будь максимально структурирован."""

        result = await self.llm.generate(
            prompt=strategic_prompt,
            task_type="strategic",
            force_cloud=True,
            temperature=0.8,
            max_tokens=4096,
        )

        return OrchestratorResponse(
            request_id=request.id,
            content=result.content,
            reasoning=reasoning_log.to_text(),
            metadata={
                "model": result.model,
                "strategic_mode": True,
                "tokens": result.tokens_used,
            },
        )

    async def _handle_autonomy_change(
        self,
        request: OrchestratorRequest,
        context: str,
        reasoning_log: ReasoningLog,
    ) -> OrchestratorResponse:
        """Handle autonomy level change requests."""
        self.reasoning.add_step(
            reasoning_log, "autonomy_change", "Запрос на изменение уровня автономности"
        )

        # This always requires explicit confirmation
        return OrchestratorResponse(
            request_id=request.id,
            content="Мистер Корган, изменение уровня автономности требует подтверждения через Telegram.",
            reasoning=reasoning_log.to_text(),
            metadata={"requires_telegram_confirmation": True},
        )

    async def _store_in_memory(
        self, request: OrchestratorRequest, response: OrchestratorResponse
    ) -> None:
        """Store the interaction in memory system."""
        try:
            await self.memory.store_message(
                role="user",
                content=request.content,
                interface=request.interface,
                metadata={"request_id": request.id},
            )
            await self.memory.store_message(
                role="assistant",
                content=response.content,
                reasoning=response.reasoning,
                interface=request.interface,
                metadata={
                    "request_id": request.id,
                    "response_id": response.id,
                    **response.metadata,
                },
            )
        except Exception as e:
            logger.error("memory_store_failed", error=str(e))

    @staticmethod
    def _intent_to_agent(intent: IntentType) -> str:
        """Map intent to agent name."""
        mapping = {
            IntentType.GIT_OPERATION: "git_agent",
            IntentType.SYSTEM_COMMAND: "powershell_agent",
            IntentType.CODE_TASK: "code_agent",
            IntentType.PROJECT_ANALYSIS: "code_agent",
            IntentType.SYSTEM_QUERY: "system_agent",
        }
        return mapping.get(intent, "")
