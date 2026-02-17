"""
KORGAN AI — Code Agent
Code analysis, review, bug finding, and quality scoring.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from core.agents.base import (
    BaseAgent, ActionPlan, ActionResult, ActionStatus, RiskLevel,
)

logger = structlog.get_logger("korgan.agent.code")


class CodeAgent(BaseAgent):
    """
    Code analysis and quality agent.
    
    Capabilities:
    - analyze_project: Structure and metrics overview
    - find_bugs: Static analysis + LLM review
    - suggest_fixes: Generate fix suggestions
    - apply_fix: Apply code changes (requires approval)
    - generate_tests: Generate test cases
    - score_quality: Code quality scoring (A-F)
    - explain_code: Code explanation
    - search_code: Search codebase
    """

    def __init__(self, llm_router: Any = None, **kwargs):
        super().__init__(
            name="code_agent",
            description="Code analysis, review, and quality scoring",
            risk_level=RiskLevel.LOW,
            **kwargs,
        )
        self._llm = llm_router

    async def plan(self, task: str, context: str = "") -> ActionPlan:
        """Plan a code operation."""
        task_lower = task.lower()

        if any(w in task_lower for w in ["analyze", "анализ", "structure"]):
            return ActionPlan(
                agent_name=self.name,
                description="Анализ проекта",
                steps=["1. Сканирование структуры", "2. Подсчёт метрик", "3. Отчёт"],
                risk_level=RiskLevel.LOW,
            )
        elif any(w in task_lower for w in ["bug", "баг", "ошибк"]):
            return ActionPlan(
                agent_name=self.name,
                description="Поиск багов",
                steps=["1. Статический анализ", "2. LLM-ревью", "3. Отчёт"],
                risk_level=RiskLevel.LOW,
            )
        elif any(w in task_lower for w in ["fix", "исправ", "patch"]):
            return ActionPlan(
                agent_name=self.name,
                description="Применение исправления",
                steps=["1. Анализ", "2. Генерация fix", "3. Preview", "4. Применение"],
                risk_level=RiskLevel.MEDIUM,
                requires_approval=True,
            )
        else:
            return ActionPlan(
                agent_name=self.name,
                description=f"Code: {task[:80]}",
                steps=["Анализ и выполнение"],
                risk_level=RiskLevel.LOW,
            )

    async def execute(self, task: str, context: str = "") -> ActionResult:
        """Execute a code operation."""
        task_lower = task.lower()

        if any(w in task_lower for w in ["analyze", "анализ", "structure", "структур"]):
            return await self.analyze_project(context)
        elif any(w in task_lower for w in ["score", "качеств", "quality"]):
            return await self.score_quality(context)
        elif any(w in task_lower for w in ["explain", "объясн"]):
            return await self.explain_code(task, context)
        else:
            return await self.analyze_project(context)

    async def analyze_project(self, project_path: str = ".") -> ActionResult:
        """Analyze project structure and metrics."""
        path = Path(project_path) if project_path != "." else Path.cwd()

        stats = {
            "total_files": 0,
            "by_extension": {},
            "total_lines": 0,
            "directories": 0,
        }

        try:
            for item in path.rglob("*"):
                # Skip hidden dirs, node_modules, __pycache__, .git
                parts = item.parts
                if any(
                    p.startswith(".") or p in ("node_modules", "__pycache__", "venv", ".git")
                    for p in parts
                ):
                    continue

                if item.is_dir():
                    stats["directories"] += 1
                elif item.is_file():
                    stats["total_files"] += 1
                    ext = item.suffix or "(no ext)"
                    stats["by_extension"][ext] = stats["by_extension"].get(ext, 0) + 1

                    # Count lines for text files
                    if ext in (".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".md", ".html", ".css"):
                        try:
                            stats["total_lines"] += sum(
                                1 for _ in open(item, "r", encoding="utf-8", errors="ignore")
                            )
                        except Exception:
                            pass

        except Exception as e:
            return ActionResult(
                agent_name=self.name,
                action_type="analyze_project",
                status=ActionStatus.FAILED,
                summary=f"Ошибка анализа: {str(e)}",
                error=str(e),
            )

        # Sort extensions by count
        sorted_ext = sorted(stats["by_extension"].items(), key=lambda x: x[1], reverse=True)

        summary = f"""Анализ проекта: {path.name}
Директорий: {stats['directories']}
Файлов: {stats['total_files']}
Строк кода: {stats['total_lines']:,}

По типам файлов:
"""
        for ext, count in sorted_ext[:15]:
            summary += f"  {ext}: {count}\n"

        return ActionResult(
            agent_name=self.name,
            action_type="analyze_project",
            summary=summary,
            output=stats,
        )

    async def score_quality(self, file_path: str = "") -> ActionResult:
        """Score code quality (A-F grade)."""
        if not file_path or not self._llm:
            return ActionResult(
                agent_name=self.name,
                action_type="score_quality",
                summary="Для оценки качества укажите файл или директорию, и убедитесь что LLM доступен.",
            )

        # Read file
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()[:8000]  # Limit for LLM context
        except Exception as e:
            return ActionResult(
                agent_name=self.name,
                action_type="score_quality",
                status=ActionStatus.FAILED,
                summary=f"Не удалось прочитать файл: {str(e)}",
                error=str(e),
            )

        # LLM-based scoring
        prompt = f"""Оцени качество следующего кода по шкале A-F.
Критерии:
- Complexity (цикломатическая сложность)
- Maintainability (читаемость, структура)
- Security (уязвимости)
- Performance (антипаттерны)

Верни JSON: {{"grade": "A-F", "complexity": "A-F", "maintainability": "A-F", "security": "A-F", "performance": "A-F", "issues": ["issue1", "issue2"], "recommendations": ["rec1"]}}

Код:
```
{code}
```"""

        result = await self._llm.generate(
            prompt=prompt,
            task_type="code_review",
            temperature=0.2,
            max_tokens=1000,
        )

        return ActionResult(
            agent_name=self.name,
            action_type="score_quality",
            summary=f"Оценка качества {file_path}:\n{result.content}",
            output=result.content,
        )

    async def explain_code(self, task: str, code_or_path: str = "") -> ActionResult:
        """Explain code using LLM."""
        if not self._llm:
            return ActionResult(
                agent_name=self.name,
                action_type="explain_code",
                summary="LLM не доступен для объяснения кода.",
            )

        # Try reading as file path
        code = code_or_path
        if os.path.isfile(code_or_path):
            try:
                with open(code_or_path, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()[:6000]
            except Exception:
                pass

        prompt = f"""Объясни следующий код кратко и структурированно.
Укажи: назначение, ключевые компоненты, поток данных.

{task}

```
{code}
```"""

        result = await self._llm.generate(
            prompt=prompt,
            task_type="code_analysis",
            temperature=0.5,
        )

        return ActionResult(
            agent_name=self.name,
            action_type="explain_code",
            summary=result.content,
        )

    async def rollback(self, action_id: str) -> bool:
        """Rollback code changes (delegates to Git agent if needed)."""
        logger.info("code_rollback_requested", action_id=action_id)
        return False
