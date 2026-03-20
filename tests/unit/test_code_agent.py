"""
KORGAN AI — Unit Tests for CodeAgent
"""

from __future__ import annotations

import pytest

from core.agents.code_agent import CodeAgent
from core.agents.base import ActionStatus


@pytest.fixture
def agent():
    return CodeAgent()


@pytest.fixture
def project_dir(tmp_path):
    """Create a small test project."""
    (tmp_path / "main.py").write_text(
        'def main():\n    print("hello")\n\nif __name__ == "__main__":\n    main()\n'
    )
    (tmp_path / "utils.py").write_text(
        "import os\n\ndef get_path():\n    return os.getcwd()\n"
    )
    (tmp_path / "bad.py").write_text(
        'password = "secret123"\nresult = eval(input())\n'
    )
    return tmp_path


class TestCodeAgent:
    @pytest.mark.asyncio
    async def test_analyze_project(self, agent, project_dir):
        result = await agent.analyze_project(str(project_dir))
        assert result.success
        assert "Файлов:" in result.summary
        assert result.output["total_files"] >= 3

    @pytest.mark.asyncio
    async def test_analyze_nonexistent(self, agent):
        result = await agent.analyze_project("/nonexistent/path/12345")
        # Should handle gracefully — either empty stats or error
        assert result.action_type == "analyze_project"

    @pytest.mark.asyncio
    async def test_find_bugs(self, agent, project_dir):
        result = await agent.find_bugs(str(project_dir))
        assert result.success
        assert result.action_type == "find_bugs"
        # Should find issues in bad.py (password, eval)
        static_issues = result.output.get("static_issues", [])
        assert len(static_issues) >= 2  # at least password + eval

    @pytest.mark.asyncio
    async def test_find_bugs_single_file(self, agent, project_dir):
        result = await agent.find_bugs(str(project_dir / "bad.py"))
        assert result.success
        assert len(result.output["static_issues"]) >= 2

    @pytest.mark.asyncio
    async def test_find_bugs_clean_file(self, agent, project_dir):
        result = await agent.find_bugs(str(project_dir / "main.py"))
        assert result.success
        # main.py should have no security issues
        static_issues = result.output["static_issues"]
        security_issues = [i for i in static_issues if "security" in i.get("issue", "").lower() or "password" in i.get("issue", "").lower()]
        assert len(security_issues) == 0

    @pytest.mark.asyncio
    async def test_find_bugs_empty_dir(self, agent, tmp_path):
        result = await agent.find_bugs(str(tmp_path))
        assert "не найдены" in result.summary.lower() or result.output == {"static_issues": [], "llm_issues": []}

    @pytest.mark.asyncio
    async def test_search_code(self, agent, project_dir):
        result = await agent.search_code("find os.getcwd", str(project_dir))
        assert result.success
        assert len(result.output) >= 1

    @pytest.mark.asyncio
    async def test_plan_analyze(self, agent):
        plan = await agent.plan("analyze project structure")
        assert plan.agent_name == "code_agent"
        assert "Анализ" in plan.description

    @pytest.mark.asyncio
    async def test_plan_bugs(self, agent):
        plan = await agent.plan("find bugs in code")
        assert "баг" in plan.description.lower() or "bug" in plan.description.lower()

    @pytest.mark.asyncio
    async def test_plan_fix_requires_approval(self, agent):
        plan = await agent.plan("fix the broken function")
        assert plan.requires_approval is True

    @pytest.mark.asyncio
    async def test_execute_routes_to_analyze(self, agent, project_dir):
        result = await agent.execute("analyze this", str(project_dir))
        assert result.action_type == "analyze_project"

    @pytest.mark.asyncio
    async def test_execute_routes_to_bugs(self, agent, project_dir):
        result = await agent.execute("find bugs", str(project_dir))
        assert result.action_type == "find_bugs"
