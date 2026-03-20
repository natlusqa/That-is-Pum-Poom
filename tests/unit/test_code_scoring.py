"""
KORGAN AI — Unit Tests for CodeQualityScorer
"""

from __future__ import annotations

import os
import tempfile

import pytest

from intelligence.code_scoring import CodeQualityScorer, QualityScore


@pytest.fixture
def scorer():
    return CodeQualityScorer()


@pytest.fixture
def good_code_file(tmp_path):
    """A well-written Python file."""
    code = '''"""Module docstring."""

import os
from typing import Optional


def calculate_sum(numbers: list[int]) -> int:
    """Calculate the sum of a list of numbers."""
    # Validate input
    if not numbers:
        return 0
    return sum(numbers)


def format_name(first: str, last: str) -> str:
    """Format full name."""
    return f"{first.strip()} {last.strip()}"


class DataProcessor:
    """Processes data records."""

    def __init__(self, source: str):
        self.source = source
        self._cache: dict = {}

    def process(self, record: dict) -> Optional[dict]:
        """Process a single record."""
        if not record:
            return None
        return {k: str(v).strip() for k, v in record.items()}
'''
    path = tmp_path / "good_code.py"
    path.write_text(code)
    return str(path)


@pytest.fixture
def bad_code_file(tmp_path):
    """A file with various code quality issues."""
    code = '''import *
password = "super_secret_123"
api_key = "sk-12345abcde"

def f(x,y,z,a,b,c,d,e,f,g,h,i,j,k,l,m,n):
    if x:
        if y:
            if z:
                if a:
                    if b:
                        if c:
                            if d:
                                return eval(str(x))
    result = os.system("rm -rf /")
    for item in items.all():
        time.sleep(10000)
        process(item)
    return None
'''
    path = tmp_path / "bad_code.py"
    path.write_text(code)
    return str(path)


class TestQualityScore:
    def test_default_score(self):
        score = QualityScore()
        assert score.overall_grade == "N/A"
        assert score.numeric_score == 0.0

    def test_to_dict(self):
        score = QualityScore(
            file_path="test.py",
            overall_grade="B",
            numeric_score=85.0,
            issues=["issue1"],
        )
        d = score.to_dict()
        assert d["file"] == "test.py"
        assert d["overall"] == "B"
        assert len(d["issues"]) == 1

    def test_to_text(self):
        score = QualityScore(
            file_path="test.py",
            overall_grade="A",
            numeric_score=95.0,
        )
        text = score.to_text()
        assert "test.py" in text
        assert "95" in text


class TestCodeQualityScorer:
    @pytest.mark.asyncio
    async def test_score_good_file(self, scorer, good_code_file):
        score = await scorer.score_file(good_code_file)
        assert score.overall_grade in ("A", "B")
        assert score.numeric_score >= 70
        assert len(score.issues) == 0  # No security issues

    @pytest.mark.asyncio
    async def test_score_bad_file(self, scorer, bad_code_file):
        score = await scorer.score_file(bad_code_file)
        assert score.overall_grade in ("D", "F")
        assert score.numeric_score < 70
        assert len(score.issues) > 0  # Security/performance issues found

    @pytest.mark.asyncio
    async def test_score_nonexistent_file(self, scorer):
        score = await scorer.score_file("/nonexistent/file.py")
        assert score.overall_grade == "ERR"

    @pytest.mark.asyncio
    async def test_score_empty_file(self, scorer, tmp_path):
        path = tmp_path / "empty.py"
        path.write_text("")
        score = await scorer.score_file(str(path))
        assert score.overall_grade == "N/A"

    def test_numeric_to_grade(self):
        assert CodeQualityScorer._numeric_to_grade(95) == "A"
        assert CodeQualityScorer._numeric_to_grade(85) == "B"
        assert CodeQualityScorer._numeric_to_grade(75) == "C"
        assert CodeQualityScorer._numeric_to_grade(65) == "D"
        assert CodeQualityScorer._numeric_to_grade(50) == "F"

    def test_security_patterns_detect_eval(self, scorer):
        code = 'result = eval(user_input)'
        score, issues = scorer._analyze_security(code)
        assert score < 100
        assert any("eval" in i.lower() for i in issues)

    def test_security_patterns_detect_hardcoded_password(self, scorer):
        code = 'password = "mysecret123"'
        score, issues = scorer._analyze_security(code)
        assert score < 100
        assert any("password" in i.lower() for i in issues)

    def test_performance_patterns_detect_sleep(self, scorer):
        code = 'time.sleep(30)'
        score, issues = scorer._analyze_performance(code)
        assert any("sleep" in i.lower() for i in issues)

    def test_complexity_deep_nesting(self, scorer):
        lines = ["    " * 8 + "pass"]  # 8 levels deep
        code = "\n".join(lines)
        score = scorer._analyze_complexity(code, lines)
        assert score < 100

    def test_maintainability_long_lines(self, scorer):
        lines = ["x" * 150 for _ in range(20)]
        code = "\n".join(lines)
        score = scorer._analyze_maintainability(code, lines)
        assert score < 100

    @pytest.mark.asyncio
    async def test_score_project(self, scorer, tmp_path):
        # Create a few files
        (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
        (tmp_path / "b.py").write_text("def bar():\n    return 2\n")

        result = await scorer.score_project(str(tmp_path))
        assert result["files_scored"] == 2
        assert "grade" in result
