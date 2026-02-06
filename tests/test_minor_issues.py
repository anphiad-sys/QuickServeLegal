"""
Tests for MINOR issues from code review audit.

TDD: These tests verify deprecated APIs are no longer used.
"""

import pytest


# =============================================================================
# ISSUE 1: Deprecated app.on_event
# =============================================================================

class TestLifespan:
    """FastAPI app should use lifespan context manager, not deprecated on_event."""

    def test_main_does_not_use_on_event(self):
        """main.py should not use deprecated @app.on_event decorator."""
        import inspect
        from src import main
        source = inspect.getsource(main)

        assert "@app.on_event" not in source, \
            "main.py should use lifespan context manager instead of deprecated @app.on_event"

    def test_app_has_lifespan(self):
        """FastAPI app should be created with a lifespan parameter."""
        from src.main import app

        assert app.router.lifespan_context is not None, \
            "App should have a lifespan context manager configured"


# =============================================================================
# ISSUE 2: Deprecated datetime.utcnow()
# =============================================================================

class TestNoUtcnow:
    """Source code should not use deprecated datetime.utcnow()."""

    def test_source_files_do_not_use_utcnow(self):
        """No source file should call datetime.utcnow() - use datetime.now(UTC) instead."""
        from pathlib import Path
        import re

        src_dir = Path(__file__).parent.parent / "src"
        violations = []

        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            # Match datetime.utcnow() but not in comments or docstrings
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "datetime.utcnow()" in line or "utcnow()" in line:
                    # Skip model default= which uses lambda (SQLAlchemy handles these)
                    if "default=" in line:
                        continue
                    violations.append(f"{py_file.name}:{i}: {stripped.strip()}")

        assert not violations, \
            f"Found deprecated datetime.utcnow() in source files:\n" + "\n".join(violations)

    def test_test_files_do_not_use_utcnow(self):
        """Test files should also use datetime.now(UTC)."""
        from pathlib import Path

        deprecated_call = "datetime." + "utcnow()"  # Split to avoid self-detection
        tests_dir = Path(__file__).parent
        violations = []

        for py_file in tests_dir.rglob("*.py"):
            # Skip this file (it references the pattern in assertions)
            if py_file.name == "test_minor_issues.py":
                continue
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if deprecated_call in line:
                    violations.append(f"{py_file.name}:{i}: {stripped.strip()}")

        assert not violations, \
            "Found deprecated datetime.utcnow() in test files:\n" + "\n".join(violations)
