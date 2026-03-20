"""
KORGAN AI — System Agent
System monitoring, health checks, and resource management.
"""

from __future__ import annotations

import platform
import subprocess
from typing import Any

import psutil
import structlog

from core.agents.base import (
    BaseAgent, ActionPlan, ActionResult, ActionStatus, RiskLevel,
)

logger = structlog.get_logger("korgan.agent.system")


class SystemAgent(BaseAgent):
    """
    System monitoring and management agent.
    
    Capabilities:
    - monitor_resources: CPU, RAM, GPU, Disk usage
    - health_check: Check all KORGAN services
    - list_processes: Running processes
    - list_services: Windows services
    - disk_usage: Disk space
    - network_status: Network info
    - cleanup_temp: Clean temp files (requires approval)
    - docker_status: Docker containers status
    """

    def __init__(self, core_services: dict[str, str] | None = None, **kwargs):
        super().__init__(
            name="system_agent",
            description="System monitoring and health management",
            risk_level=RiskLevel.MEDIUM,
            **kwargs,
        )
        # URLs of core services for health checking
        self._services = core_services or {
            "core_api": "http://localhost:8000/health",
            "voice": "http://localhost:8001/health",
            "vision": "http://localhost:8002/health",
            "ollama": "http://localhost:11434/api/tags",
            "chromadb": "http://localhost:8003/api/v1/heartbeat",
        }

    async def plan(self, task: str, context: str = "") -> ActionPlan:
        return ActionPlan(
            agent_name=self.name,
            description=f"System: {task[:80]}",
            steps=["Сбор информации", "Формирование отчёта"],
            risk_level=RiskLevel.LOW,
        )

    async def execute(self, task: str, context: str = "") -> ActionResult:
        """Route to appropriate system operation."""
        task_lower = task.lower()

        if any(w in task_lower for w in ["monitor", "ресурс", "resource", "usage"]):
            return await self.monitor_resources()
        elif any(w in task_lower for w in ["health", "здоровье", "статус"]):
            return await self.health_check()
        elif any(w in task_lower for w in ["docker", "контейнер"]):
            return await self.docker_status()
        elif any(w in task_lower for w in ["disk", "диск", "место"]):
            return await self.disk_usage()
        elif any(w in task_lower for w in ["process", "процесс"]):
            return await self.list_processes()
        else:
            return await self.monitor_resources()

    async def monitor_resources(self) -> ActionResult:
        """Get comprehensive system resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            mem = psutil.virtual_memory()

            disk = psutil.disk_usage("/" if platform.system() != "Windows" else "C:\\")

            # GPU info via nvidia-smi
            gpu_info = await self._get_gpu_info()

            report = f"""Системные ресурсы:

CPU: {cpu_percent}% ({cpu_count} ядер, {cpu_freq.current:.0f} MHz)
RAM: {mem.percent}% ({mem.used / 1024**3:.1f} / {mem.total / 1024**3:.1f} GB)
Disk C: {disk.percent}% ({disk.used / 1024**3:.0f} / {disk.total / 1024**3:.0f} GB)

GPU: {gpu_info}

OS: {platform.system()} {platform.release()} ({platform.machine()})"""

            return ActionResult(
                agent_name=self.name,
                action_type="monitor_resources",
                summary=report,
                output={
                    "cpu_percent": cpu_percent,
                    "cpu_count": cpu_count,
                    "ram_percent": mem.percent,
                    "ram_used_gb": round(mem.used / 1024**3, 1),
                    "ram_total_gb": round(mem.total / 1024**3, 1),
                    "disk_percent": disk.percent,
                    "gpu_info": gpu_info,
                },
            )
        except Exception as e:
            return ActionResult(
                agent_name=self.name,
                action_type="monitor_resources",
                status=ActionStatus.FAILED,
                summary=f"Ошибка мониторинга: {str(e)}",
                error=str(e),
            )

    async def health_check(self) -> ActionResult:
        """Check health of all KORGAN services."""
        import httpx

        results = {}
        all_healthy = True

        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, url in self._services.items():
                try:
                    resp = await client.get(url)
                    results[name] = {
                        "status": "healthy" if resp.status_code == 200 else "unhealthy",
                        "code": resp.status_code,
                    }
                except Exception as e:
                    results[name] = {"status": "down", "error": str(e)}
                    all_healthy = False

        # Format report
        lines = ["Статус сервисов KORGAN:\n"]
        for name, info in results.items():
            icon = "OK" if info["status"] == "healthy" else "FAIL"
            lines.append(f"  [{icon}] {name}: {info['status']}")

        return ActionResult(
            agent_name=self.name,
            action_type="health_check",
            status=ActionStatus.SUCCESS if all_healthy else ActionStatus.FAILED,
            summary="\n".join(lines),
            output=results,
        )

    async def docker_status(self) -> ActionResult:
        """Get Docker container status."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return ActionResult(
                agent_name=self.name,
                action_type="docker_status",
                summary=f"Docker контейнеры:\n{result.stdout}" if result.stdout else "Нет запущенных контейнеров",
                output=result.stdout,
            )
        except Exception as e:
            return ActionResult(
                agent_name=self.name,
                action_type="docker_status",
                status=ActionStatus.FAILED,
                summary=f"Ошибка Docker: {str(e)}",
                error=str(e),
            )

    async def disk_usage(self) -> ActionResult:
        """Get disk usage for all drives."""
        partitions = psutil.disk_partitions()
        lines = ["Использование дисков:\n"]

        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                lines.append(
                    f"  {part.device} ({part.mountpoint}): "
                    f"{usage.percent}% "
                    f"({usage.used / 1024**3:.0f} / {usage.total / 1024**3:.0f} GB)"
                )
            except Exception:
                pass

        return ActionResult(
            agent_name=self.name,
            action_type="disk_usage",
            summary="\n".join(lines),
        )

    async def list_processes(self, top_n: int = 15) -> ActionResult:
        """List top processes by memory usage."""
        processes = []
        for proc in psutil.process_iter(["name", "memory_percent", "cpu_percent"]):
            try:
                info = proc.info
                processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Sort by memory
        processes.sort(key=lambda x: x.get("memory_percent", 0) or 0, reverse=True)

        lines = [f"Топ-{top_n} процессов по памяти:\n"]
        for p in processes[:top_n]:
            name = p.get("name", "?")
            mem = p.get("memory_percent", 0) or 0
            cpu = p.get("cpu_percent", 0) or 0
            lines.append(f"  {name:<30} RAM: {mem:.1f}%  CPU: {cpu:.1f}%")

        return ActionResult(
            agent_name=self.name,
            action_type="list_processes",
            summary="\n".join(lines),
            output=processes[:top_n],
        )

    async def rollback(self, action_id: str) -> bool:
        """System operations are generally not rollback-able."""
        return False

    async def _get_gpu_info(self) -> str:
        """Get NVIDIA GPU information."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 5:
                    return (
                        f"{parts[0]} | VRAM: {parts[1]}/{parts[2]} MB | "
                        f"Load: {parts[3]}% | Temp: {parts[4]}°C"
                    )
            return result.stdout.strip() or "N/A"
        except Exception:
            return "nvidia-smi не доступен"
