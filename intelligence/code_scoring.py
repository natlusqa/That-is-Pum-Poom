"""
KORGAN AI — Code Quality Scoring Engine
Evaluates code quality on multiple dimensions with A-F grading.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("korgan.intelligence.code_scoring")


@dataclass
class QualityScore:
    """Code quality score for a file or project."""
    file_path: str = ""
    overall_grade: str = "N/A"
    complexity: str = "N/A"
    maintainability: str = "N/A"
    security: str = "N/A"
    performance: str = "N/A"
    test_coverage: str = "N/A"
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    numeric_score: float = 0.0  # 0-100

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "overall": self.overall_grade,
            "dimensions": {
                "complexity": self.complexity,
                "maintainability": self.maintainability,
                "security": self.security,
                "performance": self.performance,
                "test_coverage": self.test_coverage,
            },
            "numeric_score": self.numeric_score,
            "issues": self.issues,
            "recommendations": self.recommendations,
        }

    def to_text(self) -> str:
        return f"""Оценка: {self.file_path}
  Общая: {self.overall_grade} ({self.numeric_score:.0f}/100)
  Сложность: {self.complexity}
  Поддерживаемость: {self.maintainability}
  Безопасность: {self.security}
  Производительность: {self.performance}
  Тесты: {self.test_coverage}
  Проблемы: {len(self.issues)}
  Рекомендации: {len(self.recommendations)}"""


class CodeQualityScorer:
    """
    Multi-dimensional code quality scoring engine.
    
    Metrics:
    - Complexity: cyclomatic complexity, nesting depth
    - Maintainability: line length, function length, naming
    - Security: hardcoded secrets, SQL injection patterns, eval usage
    - Performance: N+1 patterns, unnecessary loops, blocking calls
    - Test Coverage: presence of tests, test-to-code ratio
    
    Grading: A (90+), B (80+), C (70+), D (60+), F (<60)
    """

    # Security patterns to detect
    SECURITY_PATTERNS = [
        (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
        (r'api_key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key"),
        (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret"),
        (r'\beval\s*\(', "Use of eval()"),
        (r'\bexec\s*\(', "Use of exec()"),
        (r'subprocess\.call\(.+shell\s*=\s*True', "Shell injection risk"),
        (r'os\.system\s*\(', "os.system() usage"),
        (r'__import__\s*\(', "Dynamic import"),
    ]

    # Performance anti-patterns
    PERFORMANCE_PATTERNS = [
        (r'for\s+.+\s+in\s+.+\.all\(\)', "Potential N+1 query"),
        (r'time\.sleep\s*\(', "Blocking sleep in async context"),
        (r'\.read\(\)(?!\s*\))', "Reading entire file into memory"),
    ]

    def __init__(self, llm_router: Any = None):
        self._llm = llm_router

    async def score_file(self, file_path: str) -> QualityScore:
        """Score a single file."""
        score = QualityScore(file_path=file_path)

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()
        except Exception as e:
            score.overall_grade = "ERR"
            score.issues.append(f"Cannot read file: {e}")
            return score

        lines = code.split("\n")
        total_lines = len(lines)

        if total_lines == 0:
            score.overall_grade = "N/A"
            return score

        # --- Complexity Analysis ---
        complexity_score = self._analyze_complexity(code, lines)
        score.complexity = self._numeric_to_grade(complexity_score)

        # --- Maintainability Analysis ---
        maintain_score = self._analyze_maintainability(code, lines)
        score.maintainability = self._numeric_to_grade(maintain_score)

        # --- Security Analysis ---
        security_score, security_issues = self._analyze_security(code)
        score.security = self._numeric_to_grade(security_score)
        score.issues.extend(security_issues)

        # --- Performance Analysis ---
        perf_score, perf_issues = self._analyze_performance(code)
        score.performance = self._numeric_to_grade(perf_score)
        score.issues.extend(perf_issues)

        # --- Test Coverage Estimate ---
        test_score = self._estimate_test_coverage(file_path)
        score.test_coverage = self._numeric_to_grade(test_score)

        # --- Overall ---
        weights = {
            "complexity": 0.25,
            "maintainability": 0.25,
            "security": 0.25,
            "performance": 0.15,
            "test_coverage": 0.10,
        }
        score.numeric_score = (
            complexity_score * weights["complexity"]
            + maintain_score * weights["maintainability"]
            + security_score * weights["security"]
            + perf_score * weights["performance"]
            + test_score * weights["test_coverage"]
        )
        score.overall_grade = self._numeric_to_grade(score.numeric_score)

        # --- LLM-enhanced recommendations ---
        if self._llm and score.numeric_score < 80:
            recommendations = await self._llm_recommendations(code[:4000], score)
            score.recommendations = recommendations

        logger.info(
            "code_scored",
            file=file_path,
            grade=score.overall_grade,
            score=score.numeric_score,
        )

        return score

    async def score_project(self, project_path: str) -> dict[str, Any]:
        """Score an entire project directory."""
        path = Path(project_path)
        scores: list[QualityScore] = []
        extensions = {".py", ".js", ".ts", ".tsx", ".jsx"}

        for file in path.rglob("*"):
            if file.suffix in extensions and not any(
                p in str(file) for p in ["node_modules", "__pycache__", ".git", "venv"]
            ):
                score = await self.score_file(str(file))
                scores.append(score)

        if not scores:
            return {"grade": "N/A", "files_scored": 0}

        avg_score = sum(s.numeric_score for s in scores) / len(scores)
        all_issues = []
        for s in scores:
            all_issues.extend(s.issues)

        return {
            "grade": self._numeric_to_grade(avg_score),
            "numeric_score": round(avg_score, 1),
            "files_scored": len(scores),
            "total_issues": len(all_issues),
            "worst_files": sorted(scores, key=lambda s: s.numeric_score)[:5],
            "best_files": sorted(scores, key=lambda s: s.numeric_score, reverse=True)[:5],
        }

    def _analyze_complexity(self, code: str, lines: list[str]) -> float:
        """Analyze code complexity."""
        score = 100.0

        # Nesting depth
        max_indent = 0
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                spaces = indent if line[0] == " " else indent * 4
                max_indent = max(max_indent, spaces // 4)

        if max_indent > 6:
            score -= 20
        elif max_indent > 4:
            score -= 10

        # Function length
        func_pattern = re.compile(r"^\s*(def |async def |function |const \w+ = )", re.MULTILINE)
        functions = func_pattern.findall(code)
        if len(lines) > 0 and len(functions) > 0:
            avg_func_length = len(lines) / len(functions)
            if avg_func_length > 50:
                score -= 15
            elif avg_func_length > 30:
                score -= 5

        # Too many lines
        if len(lines) > 500:
            score -= 10
        elif len(lines) > 300:
            score -= 5

        return max(0, score)

    def _analyze_maintainability(self, code: str, lines: list[str]) -> float:
        """Analyze maintainability."""
        score = 100.0

        # Long lines
        long_lines = sum(1 for line in lines if len(line) > 120)
        if long_lines > len(lines) * 0.1:
            score -= 15
        elif long_lines > 5:
            score -= 5

        # Comments ratio
        comment_lines = sum(1 for line in lines if line.strip().startswith("#") or line.strip().startswith("//"))
        if len(lines) > 20:
            comment_ratio = comment_lines / len(lines)
            if comment_ratio < 0.05:
                score -= 10  # Too few comments

        # Docstrings (Python)
        if '"""' in code or "'''" in code:
            score += 5  # Bonus for docstrings

        # Magic numbers
        magic_numbers = re.findall(r'(?<!["\'])\b\d{3,}\b(?!["\'])', code)
        if len(magic_numbers) > 5:
            score -= 10

        return max(0, min(100, score))

    def _analyze_security(self, code: str) -> tuple[float, list[str]]:
        """Analyze security."""
        score = 100.0
        issues = []

        for pattern, description in self.SECURITY_PATTERNS:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                score -= 20
                issues.append(f"Security: {description} ({len(matches)} occurrence(s))")

        return max(0, score), issues

    def _analyze_performance(self, code: str) -> tuple[float, list[str]]:
        """Analyze performance."""
        score = 100.0
        issues = []

        for pattern, description in self.PERFORMANCE_PATTERNS:
            matches = re.findall(pattern, code)
            if matches:
                score -= 15
                issues.append(f"Performance: {description}")

        return max(0, score), issues

    def _estimate_test_coverage(self, file_path: str) -> float:
        """Estimate test coverage by checking for test files."""
        path = Path(file_path)
        test_path = path.parent / f"test_{path.name}"
        tests_dir = path.parent.parent / "tests"

        if test_path.exists():
            return 80.0
        elif tests_dir.exists():
            return 60.0
        return 30.0

    async def _llm_recommendations(self, code: str, score: QualityScore) -> list[str]:
        """Get LLM-powered recommendations."""
        try:
            prompt = f"""Код получил оценку {score.overall_grade} ({score.numeric_score:.0f}/100).
Проблемы: {', '.join(score.issues[:5]) if score.issues else 'нет'}

Дай 3 конкретных рекомендации по улучшению. По одному предложению каждая.

Код (первые 2000 символов):
{code[:2000]}"""

            result = await self._llm.generate(
                prompt=prompt,
                task_type="code_review",
                force_local=True,
                temperature=0.3,
                max_tokens=300,
            )

            return [
                line.strip().lstrip("0123456789.-) ")
                for line in result.content.strip().split("\n")
                if line.strip() and len(line.strip()) > 10
            ][:3]
        except Exception:
            return []

    @staticmethod
    def _numeric_to_grade(score: float) -> str:
        """Convert numeric score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"
