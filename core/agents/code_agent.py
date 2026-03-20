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
        elif any(w in task_lower for w in ["bug", "баг", "ошибк", "find_bugs"]):
            return await self.find_bugs(context)
        elif any(w in task_lower for w in ["test", "тест", "generate_test"]):
            return await self.generate_tests(context)
        elif any(w in task_lower for w in ["score", "качеств", "quality"]):
            return await self.score_quality(context)
        elif any(w in task_lower for w in ["search", "поиск", "найди"]):
            return await self.search_code(task, context)
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

    async def find_bugs(self, file_or_dir: str = ".") -> ActionResult:
        """Find bugs using static analysis + LLM review."""
        import re

        target = Path(file_or_dir) if file_or_dir != "." else Path.cwd()
        files_to_check = []

        if target.is_file():
            files_to_check = [target]
        elif target.is_dir():
            for f in target.rglob("*.py"):
                if not any(
                    p in str(f)
                    for p in ["__pycache__", ".git", "venv", "node_modules"]
                ):
                    files_to_check.append(f)
            files_to_check = files_to_check[:20]  # limit

        if not files_to_check:
            return ActionResult(
                agent_name=self.name,
                action_type="find_bugs",
                summary="Файлы для анализа не найдены.",
            )

        all_issues: list[dict] = []

        # Static analysis patterns
        bug_patterns = [
            (r"except\s*:", "Bare except — catches all exceptions including SystemExit/KeyboardInterrupt"),
            (r"except\s+Exception\s*:", None),  # OK pattern, skip
            (r"\beval\s*\(", "Unsafe eval() usage — potential code injection"),
            (r"\bexec\s*\(", "Unsafe exec() usage — potential code injection"),
            (r"os\.system\s*\(", "os.system() — use subprocess instead for safety"),
            (r'password\s*=\s*["\'][^"\']{3,}["\']', "Possible hardcoded password"),
            (r'secret\s*=\s*["\'][^"\']{3,}["\']', "Possible hardcoded secret"),
            (r"TODO|FIXME|HACK|XXX", "TODO/FIXME marker found"),
            (r"import \*", "Wildcard import — pollutes namespace"),
            (r"\.format\(.*\)", None),  # not a bug
            (r"time\.sleep\s*\(\s*\d{2,}", "Long sleep() call — may block async event loop"),
        ]

        for fpath in files_to_check:
            try:
                code = fpath.read_text(encoding="utf-8", errors="ignore")
                lines = code.split("\n")

                for line_no, line in enumerate(lines, 1):
                    for pattern, description in bug_patterns:
                        if description and re.search(pattern, line, re.IGNORECASE):
                            all_issues.append({
                                "file": str(fpath),
                                "line": line_no,
                                "issue": description,
                                "code": line.strip()[:120],
                            })
            except Exception:
                continue

        # LLM-enhanced review for top files
        llm_issues = []
        if self._llm and files_to_check:
            top_file = files_to_check[0]
            try:
                code = top_file.read_text(encoding="utf-8", errors="ignore")[:6000]
                result = await self._llm.generate(
                    prompt=f"""Найди потенциальные баги и проблемы в этом Python-коде.
Верни JSON массив: [{{"line": N, "issue": "описание", "severity": "low|medium|high"}}]
Если багов нет — верни [].

```python
{code}
```""",
                    task_type="code_review",
                    force_local=True,
                    temperature=0.2,
                    max_tokens=800,
                )
                import json
                content = result.content.strip()
                start = content.find("[")
                end = content.rfind("]") + 1
                if start >= 0 and end > start:
                    llm_issues = json.loads(content[start:end])
            except Exception as e:
                logger.warning("llm_bug_review_failed", error=str(e))

        # Build report
        total = len(all_issues) + len(llm_issues)
        lines = [f"Анализ багов: {len(files_to_check)} файлов, {total} проблем найдено\n"]

        if all_issues:
            lines.append("--- Статический анализ ---")
            for issue in all_issues[:15]:
                lines.append(
                    f"  {issue['file']}:{issue['line']} — {issue['issue']}"
                )

        if llm_issues:
            lines.append("\n--- LLM-ревью ---")
            for issue in llm_issues[:10]:
                sev = issue.get("severity", "?")
                lines.append(
                    f"  [{sev}] Line {issue.get('line', '?')}: {issue.get('issue', 'N/A')}"
                )

        if not all_issues and not llm_issues:
            lines.append("Проблем не обнаружено!")

        return ActionResult(
            agent_name=self.name,
            action_type="find_bugs",
            summary="\n".join(lines),
            output={"static_issues": all_issues, "llm_issues": llm_issues},
        )

    async def generate_tests(self, file_path: str = "") -> ActionResult:
        """Generate test cases for a file using LLM."""
        if not file_path or not self._llm:
            return ActionResult(
                agent_name=self.name,
                action_type="generate_tests",
                summary="Укажите файл и убедитесь что LLM доступен.",
            )

        try:
            code = Path(file_path).read_text(encoding="utf-8", errors="ignore")[:6000]
        except Exception as e:
            return ActionResult(
                agent_name=self.name,
                action_type="generate_tests",
                status=ActionStatus.FAILED,
                summary=f"Не удалось прочитать файл: {e}",
                error=str(e),
            )

        result = await self._llm.generate(
            prompt=f"""Сгенерируй pytest-тесты для следующего Python-кода.
Используй pytest + pytest-asyncio для async-функций.
Включи: edge cases, error handling, happy path.
Верни только код тестов без пояснений.

```python
{code}
```""",
            task_type="code_generation",
            temperature=0.3,
            max_tokens=2000,
        )

        return ActionResult(
            agent_name=self.name,
            action_type="generate_tests",
            summary=f"Тесты для {file_path}:\n\n{result.content}",
            output=result.content,
        )

    async def search_code(self, query: str, project_path: str = ".") -> ActionResult:
        """Search codebase for patterns or keywords."""
        import re

        target = Path(project_path) if project_path != "." else Path.cwd()
        results = []

        # Extract search term from query
        search_term = query.lower()
        for prefix in ["search", "поиск", "найди", "find"]:
            search_term = search_term.replace(prefix, "").strip()

        for fpath in target.rglob("*.py"):
            if any(p in str(fpath) for p in ["__pycache__", ".git", "venv"]):
                continue
            try:
                for line_no, line in enumerate(
                    fpath.read_text(encoding="utf-8", errors="ignore").split("\n"),
                    1,
                ):
                    if search_term in line.lower():
                        results.append({
                            "file": str(fpath),
                            "line": line_no,
                            "content": line.strip()[:150],
                        })
            except Exception:
                continue

        summary = f"Поиск '{search_term}': {len(results)} совпадений\n"
        for r in results[:20]:
            summary += f"  {r['file']}:{r['line']} — {r['content']}\n"

        return ActionResult(
            agent_name=self.name,
            action_type="search_code",
            summary=summary,
            output=results[:50],
        )

    async def rollback(self, action_id: str) -> bool:
        """Rollback code changes (delegates to Git agent if needed)."""
        logger.info("code_rollback_requested", action_id=action_id)
        return False
