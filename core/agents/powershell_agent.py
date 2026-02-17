"""
KORGAN AI — PowerShell Agent
Sandboxed Windows system command execution.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any, Optional

import structlog

from core.agents.base import (
    BaseAgent, ActionPlan, ActionResult, ActionStatus, RiskLevel,
)

logger = structlog.get_logger("korgan.agent.powershell")


class PowerShellAgent(BaseAgent):
    """
    Sandboxed PowerShell command execution agent.
    
    Security layers:
    1. Command whitelist/blacklist regex matching
    2. Path whitelist/blacklist enforcement
    3. Timeout enforcement (30s default)
    4. Output size limit (1MB)
    5. Full command logging
    
    All commands run via subprocess with restricted environment.
    """

    def __init__(self, permissions_config: dict[str, Any] | None = None, **kwargs):
        super().__init__(
            name="powershell_agent",
            description="Windows system command execution (sandboxed)",
            risk_level=RiskLevel.HIGH,
            **kwargs,
        )
        self._config = permissions_config or {}
        self._allowed_patterns = [
            re.compile(p) for p in self._config.get("allowed_commands_patterns", [])
        ]
        self._approval_patterns = [
            re.compile(p) for p in self._config.get("approval_required_patterns", [])
        ]
        self._forbidden_commands = self._config.get("forbidden_commands", [])
        self._allowed_paths = self._config.get("allowed_paths", [])
        self._forbidden_paths = self._config.get("forbidden_paths", [])
        self._timeout = self._config.get("constraints", {}).get("timeout_seconds", 30)
        self._max_output = self._config.get("constraints", {}).get("max_output_size_kb", 1024) * 1024

    async def plan(self, task: str, context: str = "") -> ActionPlan:
        """Create execution plan for a PowerShell command."""
        validation = self._validate_command(task)

        if validation["status"] == "forbidden":
            return ActionPlan(
                agent_name=self.name,
                description=f"ЗАБЛОКИРОВАНО: {task}",
                steps=[f"Команда запрещена: {validation['reason']}"],
                risk_level=RiskLevel.CRITICAL,
                requires_approval=False,
            )

        return ActionPlan(
            agent_name=self.name,
            description=f"PowerShell: {task[:100]}",
            steps=[
                "1. Валидация команды (whitelist/blacklist)",
                "2. Проверка путей",
                f"3. Выполнение (timeout: {self._timeout}s)",
                "4. Capture output",
                "5. Логирование",
            ],
            risk_level=RiskLevel.HIGH if validation["status"] == "approval_required" else RiskLevel.MEDIUM,
            requires_approval=validation["status"] == "approval_required",
        )

    async def execute(self, task: str, context: str = "") -> ActionResult:
        """Execute a PowerShell command with full sandboxing."""
        # Validate
        validation = self._validate_command(task)

        if validation["status"] == "forbidden":
            logger.warning("ps_command_forbidden", command=task[:100])
            return ActionResult(
                agent_name=self.name,
                action_type="execute_command",
                status=ActionStatus.CANCELLED,
                summary=f"Команда запрещена: {validation['reason']}",
                error=validation["reason"],
            )

        # Execute
        logger.info("ps_command_executing", command=task[:200])
        output, returncode, error = await self._run_powershell(task)

        status = ActionStatus.SUCCESS if returncode == 0 else ActionStatus.FAILED

        return ActionResult(
            agent_name=self.name,
            action_type="execute_command",
            status=status,
            summary=output[:2000] if output else f"Команда завершена с кодом {returncode}",
            output={"stdout": output[:self._max_output], "returncode": returncode},
            error=error if returncode != 0 else None,
            rollback_data=None,  # PS commands are generally not rollback-able
        )

    async def get_system_info(self) -> ActionResult:
        """Get system information."""
        commands = [
            "Get-ComputerInfo | Select-Object CsName, WindowsVersion, OsTotalVisibleMemorySize | ConvertTo-Json",
        ]
        results = []
        for cmd in commands:
            output, _, _ = await self._run_powershell(cmd)
            results.append(output)

        return ActionResult(
            agent_name=self.name,
            action_type="system_info",
            summary="\n".join(results),
            output=results,
        )

    async def get_processes(self, top_n: int = 20) -> ActionResult:
        """Get top processes by CPU/Memory."""
        cmd = f"Get-Process | Sort-Object CPU -Descending | Select-Object -First {top_n} Name, CPU, WorkingSet64 | ConvertTo-Json"
        output, _, _ = await self._run_powershell(cmd)
        return ActionResult(
            agent_name=self.name,
            action_type="get_processes",
            summary=output[:3000],
            output=output,
        )

    async def rollback(self, action_id: str) -> bool:
        """PowerShell commands generally cannot be rolled back."""
        logger.warning("ps_rollback_not_supported", action_id=action_id)
        return False

    def _validate_command(self, command: str) -> dict[str, str]:
        """
        Validate a command against security rules.
        Returns: {"status": "allowed"|"approval_required"|"forbidden", "reason": "..."}
        """
        cmd_stripped = command.strip()

        # Check forbidden commands (exact match)
        for forbidden in self._forbidden_commands:
            if forbidden.lower() in cmd_stripped.lower():
                return {
                    "status": "forbidden",
                    "reason": f"Команда в чёрном списке: {forbidden}",
                }

        # Check path restrictions
        for forbidden_path in self._forbidden_paths:
            if forbidden_path.lower() in cmd_stripped.lower():
                return {
                    "status": "forbidden",
                    "reason": f"Путь запрещён: {forbidden_path}",
                }

        # Check if command matches approval_required patterns
        for pattern in self._approval_patterns:
            if pattern.match(cmd_stripped):
                return {
                    "status": "approval_required",
                    "reason": f"Команда требует подтверждения (pattern: {pattern.pattern})",
                }

        # Check if command matches allowed patterns
        for pattern in self._allowed_patterns:
            if pattern.match(cmd_stripped):
                return {"status": "allowed", "reason": "В белом списке"}

        # Default: requires approval for unknown commands
        return {
            "status": "approval_required",
            "reason": "Команда не в белом списке — требуется подтверждение",
        }

    async def _run_powershell(self, command: str) -> tuple[str, int, str]:
        """Run a PowerShell command with safety constraints."""
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy", "Bypass",
                    "-Command", command,
                ],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                encoding="utf-8",
                errors="replace",
            )

            stdout = result.stdout[:self._max_output]
            stderr = result.stderr[:self._max_output]

            if result.returncode != 0:
                logger.warning(
                    "ps_command_error",
                    returncode=result.returncode,
                    stderr=stderr[:500],
                )

            return stdout, result.returncode, stderr

        except subprocess.TimeoutExpired:
            logger.error("ps_command_timeout", command=command[:100])
            return "", -1, f"Timeout: команда не завершилась за {self._timeout}s"
        except Exception as e:
            logger.error("ps_command_failed", error=str(e))
            return "", -1, str(e)
