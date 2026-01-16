# Test Coverage Status

Last Updated: January 16, 2026

## Overall Coverage: 35.10%

**Total**: 171 tests passing
**Goal**: 80%+ coverage

## Coverage by Module

### ✅ Excellent Coverage (>90%)

| Module | Coverage | Tests | Status |
|--------|----------|-------|--------|
| `config.py` | 95.56% | 38 tests | ✅ Excellent |
| `performance_scoring.py` | 97.37% | 22 tests | ✅ Excellent |
| `date_ranges.py` | 100% | 40 tests | ✅ Perfect |
| `repo_cache.py` | 100% | 15 tests | ✅ Perfect |
| `logging/config.py` | 93.75% | 31 tests | ✅ Excellent |
| `logging/console.py` | 97.96% | 31 tests | ✅ Excellent |
| `logging/detection.py` | 94.74% | 31 tests | ✅ Excellent |
| `logging/formatters.py` | 90.32% | 31 tests | ✅ Excellent |
| `logging/handlers.py` | 90.74% | 31 tests | ✅ Excellent |

### 🟡 Medium Coverage (50-90%)

| Module | Coverage | Missing Lines | Priority |
|--------|----------|---------------|----------|
| `dashboard/app.py` | 50.98% | 338 lines | Medium |

### 🔴 Needs Improvement (<50%)

| Module | Coverage | Missing Lines | Priority |
|--------|----------|---------------|----------|
| `metrics.py` | 19.39% | 158 lines | High |
| `dora_metrics.py` | 4.76% | 260 lines | High |
| `jira_metrics.py` | 7.41% | 100 lines | High |
| `github_graphql_collector.py` | 6.03% | 436 lines | Critical |
| `jira_collector.py` | 6.54% | 400 lines | Critical |
| `jira_filters.py` | 0% | 40 lines | Medium |

## Test Organization

```
tests/
├── unit/                   # Pure logic tests (108 tests)
│   ├── test_config.py              # 38 tests ✅
│   ├── test_performance_score.py   # 22 tests ✅
│   ├── test_logging.py             # 31 tests ✅
│   ├── test_date_ranges.py         # 40 tests ✅
│   ├── utils/
│   │   └── test_repo_cache.py      # 15 tests ✅
│   ├── test_dora_metrics.py        # Needs expansion
│   ├── test_metrics_calculator.py  # Needs expansion
│   └── test_jira_filters.py        # Exists but 0% coverage
├── dashboard/              # Dashboard tests (18 tests)
│   └── test_app.py                 # 18 export tests ✅
├── collectors/             # Collector tests (minimal)
│   ├── test_github_graphql_collector.py  # Needs work
│   └── test_jira_collector.py            # Needs work
└── integration/            # Integration tests (minimal)
    └── test_collection_workflow.py       # Needs expansion
```

## Priority Improvements

### Phase 1: High-Impact, Low-Effort (2-3 days)
1. **jira_filters.py** - Add 10-15 tests for JQL filter construction (0% → 80%+)
2. **metrics.py** - Add tests for calculation methods (19% → 60%+)
3. **dashboard/app.py** - Add route tests and helper function tests (51% → 70%+)

### Phase 2: Critical Infrastructure (1 week)
4. **github_graphql_collector.py** - Add integration tests with mocked API (6% → 40%+)
   - Test query construction
   - Test pagination handling
   - Test error recovery
5. **jira_collector.py** - Add integration tests with mocked API (7% → 40%+)
   - Test filter queries
   - Test issue parsing
   - Test release collection

### Phase 3: Complex Business Logic (1 week)
6. **dora_metrics.py** - Add DORA calculation tests (5% → 70%+)
   - Deployment frequency calculation
   - Lead time calculation
   - Change failure rate
   - MTTR calculation
7. **jira_metrics.py** - Add Jira metrics tests (7% → 70%+)

## Testing Strategy

### Current Strengths
- ✅ Excellent coverage for utilities (config, logging, date ranges, caching)
- ✅ Good test organization with clear separation
- ✅ Fast test execution (~2-3 seconds for 171 tests)
- ✅ pytest fixtures for consistent test data

### Gap Areas
- 🔴 **Collectors**: Need integration tests with mocked APIs
- 🔴 **Models**: Need unit tests for calculation logic
- 🔴 **Dashboard**: Need route tests and template rendering tests

### Recommended Approach
1. **Mock External Dependencies**: Use `pytest-mock` for API calls
2. **Fixture Expansion**: Create more realistic test data in `tests/fixtures/`
3. **Integration Tests**: Test end-to-end workflows with mocked data
4. **Error Path Testing**: Add tests for error handling and edge cases

## Quick Commands

```bash
# Run all tests with coverage
pytest --cov=src --cov-report=html --cov-report=term-missing

# Run specific module tests
pytest tests/unit/test_config.py --cov=src/config -v

# Generate HTML coverage report
pytest --cov=src --cov-report=html
open htmlcov/index.html

# Run fast tests only
pytest -m "not slow" --cov=src
```

## Coverage Targets

| Target | Deadline | Current | Gap |
|--------|----------|---------|-----|
| Utilities | ✅ Done | 95%+ | - |
| Models | Q1 2026 | 10% | +60% needed |
| Collectors | Q1 2026 | 6% | +64% needed |
| Dashboard | Q2 2026 | 51% | +29% needed |
| **Overall** | **Q2 2026** | **35%** | **+45% needed** |

## Resources

- pytest documentation: https://docs.pytest.org/
- pytest-cov: https://pytest-cov.readthedocs.io/
- pytest-mock: https://pytest-mock.readthedocs.io/
- Coverage.py: https://coverage.readthedocs.io/
