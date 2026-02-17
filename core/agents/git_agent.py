"""
KORGAN AI — Git Agent
Full Git workflow: analyze, diff, patch, dry-run, commit, push with logging.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional

import structlog

from core.agents.base import (
    BaseAgent, ActionPlan, ActionResult, ActionStatus, RiskLevel,
)

logger = structlog.get_logger("korgan.agent.git")


class GitAgent(BaseAgent):
    """
    Git operations agent with full workflow support.
    
    Capabilities:
    - analyze_diff: Show current changes
    - generate_patch: Create patch files
    - dry_run: Simulate commit/push
    - commit: Commit with message (requires approval)
    - push: Push to remote (requires approval)
    - create_branch: Create new branch
    - review_code: Automated code review
    - log_history: Analyze git log
    - status: Git status
    - list_branches: List branches
    
    All destructive operations store rollback data.
    """

    def __init__(self, **kwargs):
        super().__init__(
            name="git_agent",
            description="Git repository operations agent",
            risk_level=RiskLevel.MEDIUM,
            **kwargs,
        )
        self._default_repo_path: Optional[str] = None

    def set_repo_path(self, path: str) -> None:
        """Set the default repository path."""
        self._default_repo_path = path

    async def plan(self, task: str, context: str = "") -> ActionPlan:
        """Create a plan for the Git operation."""
        task_lower = task.lower()

        if any(w in task_lower for w in ["commit", "коммит"]):
            return ActionPlan(
                agent_name=self.name,
                description=f"Git commit: {task}",
                steps=[
                    "1. Проверить git status",
                    "2. Показать git diff",
                    "3. Сформировать commit message",
                    "4. Dry-run: git commit --dry-run",
                    "5. Запросить подтверждение у Мистера Коргана",
                    "6. Выполнить git commit",
                    "7. Логировать результат",
                ],
                risk_level=RiskLevel.MEDIUM,
                requires_approval=True,
                rollback_possible=True,
            )
        elif any(w in task_lower for w in ["push", "пуш"]):
            return ActionPlan(
                agent_name=self.name,
                description=f"Git push: {task}",
                steps=[
                    "1. Проверить git status",
                    "2. Проверить remote",
                    "3. Dry-run: git push --dry-run",
                    "4. Запросить подтверждение",
                    "5. Выполнить git push",
                    "6. Логировать результат",
                ],
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                rollback_possible=False,
            )
        elif any(w in task_lower for w in ["diff", "изменения", "changes"]):
            return ActionPlan(
                agent_name=self.name,
                description="Анализ текущих изменений",
                steps=["1. git diff", "2. Анализ изменений", "3. Сводка"],
                risk_level=RiskLevel.LOW,
                requires_approval=False,
            )
        else:
            return ActionPlan(
                agent_name=self.name,
                description=f"Git операция: {task}",
                steps=["1. Анализ запроса", "2. Выполнение", "3. Отчёт"],
                risk_level=RiskLevel.LOW,
                requires_approval=False,
            )

    async def execute(self, task: str, context: str = "") -> ActionResult:
        """Execute a Git operation."""
        task_lower = task.lower()

        if any(w in task_lower for w in ["status", "статус"]):
            return await self.status()
        elif any(w in task_lower for w in ["diff", "изменения"]):
            return await self.analyze_diff()
        elif any(w in task_lower for w in ["log", "история", "history"]):
            return await self.log_history()
        elif any(w in task_lower for w in ["branch", "ветк"]):
            return await self.list_branches()
        elif any(w in task_lower for w in ["commit", "коммит"]):
            # Extract message from task or generate
            message = task.replace("commit", "").replace("коммит", "").strip()
            if not message:
                message = "Auto-commit by KORGAN AI"
            return await self.commit(message)
        else:
            return await self.status()

    async def status(self, repo_path: str | None = None) -> ActionResult:
        """Get git status."""
        path = repo_path or self._default_repo_path
        output = await self._run_git(["status", "--short"], path)
        return ActionResult(
            agent_name=self.name,
            action_type="status",
            summary=f"Git status:\n{output}" if output else "Рабочее дерево чисто.",
            output=output,
        )

    async def analyze_diff(self, repo_path: str | None = None) -> ActionResult:
        """Analyze current diff."""
        path = repo_path or self._default_repo_path

        # Staged changes
        staged = await self._run_git(["diff", "--cached", "--stat"], path)
        # Unstaged changes
        unstaged = await self._run_git(["diff", "--stat"], path)

        diff_detail = await self._run_git(["diff"], path)

        summary_parts = []
        if staged:
            summary_parts.append(f"Staged:\n{staged}")
        if unstaged:
            summary_parts.append(f"Unstaged:\n{unstaged}")
        if not summary_parts:
            summary_parts.append("Нет изменений.")

        return ActionResult(
            agent_name=self.name,
            action_type="analyze_diff",
            summary="\n\n".join(summary_parts),
            output={"staged": staged, "unstaged": unstaged, "diff": diff_detail[:5000]},
        )

    async def commit(
        self,
        message: str,
        repo_path: str | None = None,
        add_all: bool = True,
    ) -> ActionResult:
        """Commit changes with full dry-run and logging."""
        path = repo_path or self._default_repo_path

        # Get pre-commit state for rollback
        current_head = await self._run_git(["rev-parse", "HEAD"], path)

        # Stage all changes if requested
        if add_all:
            await self._run_git(["add", "-A"], path)

        # Dry run
        dry_run = await self._run_git(
            ["commit", "--dry-run", "-m", message], path
        )
        logger.info("git_commit_dry_run", result=dry_run[:500])

        # Actual commit
        output = await self._run_git(["commit", "-m", message], path)

        new_head = await self._run_git(["rev-parse", "HEAD"], path)

        return ActionResult(
            agent_name=self.name,
            action_type="commit",
            summary=f"Коммит выполнен: {message}\n{output}",
            output={"message": message, "old_head": current_head, "new_head": new_head},
            rollback_data={
                "type": "git_reset",
                "target_commit": current_head.strip() if current_head else None,
                "repo_path": path,
            },
        )

    async def push(
        self, remote: str = "origin", branch: str | None = None, repo_path: str | None = None
    ) -> ActionResult:
        """Push to remote with dry-run."""
        path = repo_path or self._default_repo_path

        if not branch:
            branch = await self._run_git(["branch", "--show-current"], path)
            branch = branch.strip()

        # Dry run
        dry_run = await self._run_git(
            ["push", "--dry-run", remote, branch], path
        )
        logger.info("git_push_dry_run", result=dry_run[:500])

        # Actual push
        output = await self._run_git(["push", remote, branch], path)

        return ActionResult(
            agent_name=self.name,
            action_type="push",
            summary=f"Push выполнен: {remote}/{branch}\n{output}",
            output={"remote": remote, "branch": branch, "result": output},
        )

    async def log_history(
        self, count: int = 10, repo_path: str | None = None
    ) -> ActionResult:
        """Get recent git log."""
        path = repo_path or self._default_repo_path
        output = await self._run_git(
            ["log", f"--oneline", f"-{count}", "--decorate"], path
        )
        return ActionResult(
            agent_name=self.name,
            action_type="log_history",
            summary=f"Последние {count} коммитов:\n{output}" if output else "Нет истории коммитов.",
            output=output,
        )

    async def list_branches(self, repo_path: str | None = None) -> ActionResult:
        """List all branches."""
        path = repo_path or self._default_repo_path
        output = await self._run_git(["branch", "-a", "--format=%(refname:short)"], path)
        return ActionResult(
            agent_name=self.name,
            action_type="list_branches",
            summary=f"Ветки:\n{output}" if output else "Нет веток.",
            output=output,
        )

    async def rollback(self, action_id: str) -> bool:
        """Rollback a git commit using stored rollback data."""
        # In production, retrieve rollback_data from audit log by action_id
        logger.warning("git_rollback_requested", action_id=action_id)
        return False  # Placeholder — needs rollback_data retrieval

    async def rollback_commit(self, target_commit: str, repo_path: str | None = None) -> ActionResult:
        """Rollback to a specific commit (soft reset)."""
        path = repo_path or self._default_repo_path
        output = await self._run_git(["reset", "--soft", target_commit], path)
        return ActionResult(
            agent_name=self.name,
            action_type="rollback_commit",
            summary=f"Откат к коммиту {target_commit[:8]}",
            output=output,
        )

    async def _run_git(self, args: list[str], repo_path: str | None = None) -> str:
        """Run a git command safely."""
        cmd = ["git"] + args
        cwd = repo_path or os.getcwd()

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout + result.stderr
            if result.returncode != 0:
                logger.warning(
                    "git_command_error",
                    cmd=" ".join(cmd),
                    returncode=result.returncode,
                    stderr=result.stderr[:500],
                )
            return output.strip()
        except subprocess.TimeoutExpired:
            logger.error("git_command_timeout", cmd=" ".join(cmd))
            return "ERROR: Git command timed out (30s)"
        except Exception as e:
            logger.error("git_command_failed", cmd=" ".join(cmd), error=str(e))
            return f"ERROR: {str(e)}"
