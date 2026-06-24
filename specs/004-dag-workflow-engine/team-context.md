## Discovered Team Context

| ID | Module | Type | Descriptor | Relevance |
|----|--------|------|------------|-----------|
| CDR-2026-022 | context_modules/rules/style-guides/file_organization.md | Rule | File organization and structure conventions | Medium |
| CDR-2026-025 | context_modules/rules/style-guides/python/pep8_and_docstrings.md | Rule | Python PEP 8 conventions and docstring standards | Medium |
| CDR-2026-027 | context_modules/rules/testing/python/pytest_patterns.md | Rule | Pytest testing patterns and conventions for Python | Medium |

### CDR-2026-025: Python Style Guide
**Checklist**:
- Follow PEP 8 formatting (4-space indents, 79 char lines unless blackened).
- Use type hints on public functions.
- Write module, class, and function docstrings describing purpose, params, and return values.
- Prefer f-strings over % formatting or str.format.
- Run ruff or flake8 plus black before submitting changes.

### CDR-2026-027: Python Testing with Pytest
**Checklist**:
- Use pytest for all new test suites
- Organize tests with class-based grouping for related test scenarios
- Use fixtures in conftest.py for shared test data
- Apply pytest.mark.parametrize for testing multiple inputs
- Mock external dependencies (databases, APIs, file systems) not code under test
- Use descriptive test method names following pytest conventions

### CDR-2026-022: File Organization
**Key rules**:
- Target 200-400 lines per file, maximum 800
- Target <50 lines per function/method, maximum 100
- Keep nesting depth manageable

_Searched 27 CDR entries, 3 medium matches found (no high-relevance matches for this feature domain)._
