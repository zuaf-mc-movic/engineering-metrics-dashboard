# Code Quality Guide

This document describes the code quality tools and standards for the Team Metrics Dashboard project.

## Tools Setup

### Installed Tools

All code quality tools are configured in `pyproject.toml`:

- **Black** - Opinionated code formatter (line length: 120)
- **isort** - Import statement organizer (compatible with Black)
- **Pylint** - Comprehensive linter (score: 9.28/10 ✅)
- **Mypy** - Static type checker

### Installation

```bash
# Install in virtual environment
source venv/bin/activate
pip install black isort pylint mypy

# Or install all dev dependencies
pip install -e ".[dev]"
```

### Quick Commands

```bash
# Format code
black src/ collect_data.py list_jira_filters.py validate_config.py analyze_releases.py

# Organize imports
isort src/ collect_data.py list_jira_filters.py validate_config.py analyze_releases.py

# Run linter
pylint src/

# Run type checker
mypy src/

# Run all in sequence
black src/ && isort src/ && pylint src/ && mypy src/
```

## Pre-commit Hooks (Optional)

Pre-commit hooks automatically run checks before each commit.

### Setup

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### Configuration

See `.pre-commit-config.yaml` for hook configuration. By default:
- **Black** and **isort** run on every commit (auto-fix)
- **Pylint** and **mypy** run manually only (informational)

## Current Status

### Pylint Score: 9.28/10 ✅

**Top Issues to Address:**
1. **Too many branches/statements** in large functions (refactoring needed)
2. **Import-outside-toplevel** in several places (move to top)
3. **Bare-except** clauses (specify exception types)
4. **Unused imports** (clean up imports)
5. **Line too long** (a few lines exceed 120 chars)

**Disabled Checks** (see `pyproject.toml`):
- `C0103` - invalid-name (we use short names like 'df', 'pr', 'jql')
- `C0114/115/116` - missing-docstring (focus on public APIs)
- `R0913` - too-many-arguments (common in data processing)
- `R0914` - too-many-locals (will address in refactoring)

### Mypy Type Checking

**Status: ✅ 100% Type Safe - 0 errors across 22 source files on ALL Python versions (3.9-3.12)**

**Achievement Timeline:**
- **Initial State** (Jan 2026): 78 type errors across 9 files
- **First Pass** (Jan 14, 2026): Reduced to 8 errors (90% reduction) - [Commit 2f03a3d](../../commit/2f03a3d)
- **Second Pass** (Jan 16, 2026): **0 errors on Python 3.10-3.12** - [Commit f012235](../../commit/f012235)
- **Final Fix** (Jan 16, 2026): **0 errors on Python 3.9** (100% reduction) - [Commits f36e01a, bdb7385](../../commit/bdb7385)

**Key Improvements Made:**

1. **✅ Fixed "Returning Any" errors** (5 fixes)
   - `repo_cache.py`: Cast JSON repositories to `List[str]`
   - `logging/config.py`: Cast YAML config to `Dict[Any, Any]`
   - `github_graphql_collector.py`: Cast GraphQL API responses to `Dict[Any, Any]`
   - `app.py`: Cast pandas DataFrame records to `List[Any]` and comparison results to `bool`

2. **✅ Fixed assignment type errors** (2 fixes)
   - `github_graphql_collector.py`: Added explicit type annotation for payload dict
   - `logging/handlers.py`: Added type ignore for standard RotatingFileHandler pattern

3. **✅ Fixed nested function return types** (1 fix)
   - `app.py`: Changed `datetime_handler` to raise `TypeError` for non-datetime objects (matches standard JSON serializer)

4. **✅ Fixed Python 3.9 compatibility** (6 type assertions - Jan 16, 2026)
   - **Root Cause**: Python 3.9's type narrowing cannot resolve `jira` library's union return types
   - **Solution**: Added explicit `cast(List[Issue], ...)` assertions at all `search_issues()` call sites
   - **Locations Fixed**:
     - `jira_collector.py:79` - `collect_issue_metrics()`
     - `jira_collector.py:171` - `collect_worklog_metrics()`
     - `jira_collector.py:220` - `collect_person_issues()`
     - `jira_collector.py:306` - `collect_filter_issues()`
     - `jira_collector.py:621` - `collect_incidents()`
     - `jira_collector.py:1009` - `_get_issues_for_version()`
   - **Result**: Type assertions make our understanding of jira API types explicit
   - **CI**: Removed `continue-on-error` flag to enable strict type checking

5. **✅ Added proper type imports**
   - Added `cast` from typing to 6 critical files for runtime type assertions
   - Imported `Issue` type from jira library for explicit type annotations

**Type Hint Coverage by Module:**

| Module | Coverage | Status |
|--------|----------|--------|
| All 22 source files | 100% type safe | ✅ Excellent |
| `jira_collector.py` | No type errors | ✅ Excellent |
| `github_graphql_collector.py` | No type errors | ✅ Excellent |
| `performance_scoring.py` | No type errors | ✅ Excellent |
| `metrics.py` | No type errors | ✅ Excellent |
| `dora_metrics.py` | No type errors | ✅ Excellent |
| `jira_metrics.py` | No type errors | ✅ Excellent |
| `app.py` | No type errors | ✅ Excellent |
| `config.py` | No type errors | ✅ Excellent |

**CI/CD Integration:**
- GitHub Actions workflow validates type safety across Python 3.9, 3.10, 3.11, and 3.12
- All quality gates passing on every commit to `main` branch
- Strict type checking enabled (`continue-on-error: false`) - any type error fails the build
- Python 3.9 compatibility confirmed: 0 errors (previously had 74 errors before fix)

### Black Formatting

**Result: 18 files reformatted** ✅

All code now follows Black style guide (120 char line length, consistent quotes, trailing commas).

### isort Import Organization

**Result: 12 files reorganized** ✅

All imports now follow the standard order:
1. Standard library imports
2. Third-party imports
3. Local application imports

## Code Complexity

### Module Complexity Status

**✅ Refactoring Complete!** The original monolithic `metrics.py` (1,604 lines) has been split into 4 focused modules:

| Module | Lines | Focus | Status |
|--------|-------|-------|--------|
| `metrics.py` | 605 | Core orchestration | ✅ Refactored |
| `dora_metrics.py` | 635 | DORA four key metrics | ✅ Extracted |
| `performance_scoring.py` | 270 | Performance scoring utilities | ✅ Extracted |
| `jira_metrics.py` | 226 | Jira filter processing | ✅ Extracted |

**Key Improvements:**
- Reduced complexity by separating concerns
- Used mixin pattern for DORAMetrics and JiraMetrics
- Delegated performance scoring to static utility class
- Maintained 100% backward compatibility
- All 66 tests pass

**Largest Remaining Functions:**

| Function | File | Lines | Complexity | Status |
|----------|------|-------|------------|--------|
| `calculate_team_metrics` | metrics.py | 53 | Low | ✅ Much improved |
| `_calculate_lead_time_for_changes` | dora_metrics.py | 174 | Medium | 🟢 OK (domain complexity) |
| `_collect_repository_metrics_batched` | github_graphql_collector.py | 75 | Medium | 🟢 OK |

## Recommended Workflow

### Daily Development

1. Write code as normal
2. Before committing:
   ```bash
   black src/
   isort src/
   ```
3. Commit changes

### Before Pull Request

1. Run full linting:
   ```bash
   pylint src/
   ```
2. Address critical issues (score should stay above 9.0)
3. Run type checking:
   ```bash
   mypy src/
   ```
4. Run tests:
   ```bash
   pytest
   ```

### CI/CD Integration

Add to CI pipeline (`.github/workflows/quality.yml`):

```yaml
- name: Check code quality
  run: |
    pip install black isort pylint mypy
    black --check src/
    isort --check-only src/
    pylint src/ --fail-under=9.0
    mypy src/
```

## Configuration Details

### Black Configuration

```toml
[tool.black]
line-length = 120
target-version = ['py38', 'py39', 'py310', 'py311']
```

**Why 120 chars?** Modern displays support wider lines, and data processing code benefits from longer lines for readability.

### Pylint Configuration

See `pyproject.toml` for full configuration. Key settings:

- **max-line-length**: 120 (matches Black)
- **max-args**: 10 (will reduce during refactoring)
- **max-locals**: 20 (will reduce during refactoring)
- **max-branches**: 15 (currently exceeded in 5 functions)
- **max-statements**: 60 (currently exceeded in 4 functions)

### Mypy Configuration

Starting with permissive settings, will gradually tighten:

- **python_version**: 3.8 (minimum supported)
- **disallow_untyped_defs**: false (start permissive)
- **ignore_missing_imports**: true (many libs lack stubs)
- **no_implicit_optional**: true (enforce explicit Optional)

## Completed Work

### ✅ Phase 1: Type Safety (COMPLETED - Jan 2026)

1. ~~**Add type hints to app.py**~~ - ✅ **COMPLETED!** All type errors fixed
2. ~~**Install type stubs**~~ - ✅ **COMPLETED!** types-PyYAML and types-requests installed
3. ~~**Fix implicit Optional**~~ - ✅ **COMPLETED!** All Optional[] annotations added
4. ~~**Fix all mypy errors**~~ - ✅ **COMPLETED!** 0 errors across 22 source files

### ✅ Phase 2: Code Refactoring (COMPLETED - Jan 2026)

5. ~~**Split metrics.py**~~ - ✅ **COMPLETED!** Created 4 focused modules:
   - `metrics.py` (605 lines - core orchestration)
   - `dora_metrics.py` (635 lines - DORA calculations)
   - `performance_scoring.py` (270 lines - scoring system)
   - `jira_metrics.py` (226 lines - Jira processing)

## Next Steps

### Phase 3: Code Quality Polish

6. **Improve Pylint score** - Address remaining warnings to reach 10.0/10
   - Fix bare-except clauses (specify exception types)
   - Remove unused imports
   - Move imports to top (eliminate import-outside-toplevel)
   - Reduce complexity in remaining large functions

7. **Advanced type hints** - Go beyond basic type safety
   - Add TypedDict for structured data (metrics dictionaries)
   - Enable stricter mypy flags (--disallow-any-generics, --warn-return-any)
   - Add generic types for collection returns

### Phase 4: Test Coverage

8. **Increase test coverage** - Target 80%+ overall coverage
   - Add tests for collectors (currently ~6-7% coverage)
   - Add integration tests for dashboard routes
   - Add tests for DORA metrics calculations
   - Add tests for error handling paths

### Phase 5: Development Workflow

9. **Add pre-commit hooks** - Prevent quality regressions
   - Configure .pre-commit-config.yaml with mypy, black, isort
   - Add automatic fixing on commit
   - Add pre-push test running

### Phase 6: Advanced Improvements (Future)

10. **Refactor DORA functions** - Extract common patterns
11. **Introduce Flask blueprints** - Split app.py into modules
12. **Performance optimization** - Profile and optimize hot paths

## Resources

- **Black**: https://black.readthedocs.io/
- **isort**: https://pycqa.github.io/isort/
- **Pylint**: https://pylint.readthedocs.io/
- **Mypy**: https://mypy.readthedocs.io/
- **Pre-commit**: https://pre-commit.com/

## Questions?

For questions about code quality standards or tooling, see:
- `pyproject.toml` - All tool configurations
- `CLAUDE.md` - Development workflow
- This file - Code quality guidelines
