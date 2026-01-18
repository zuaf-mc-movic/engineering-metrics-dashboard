"""Integration tests for parallel collection workflows

Tests the ThreadPoolExecutor-based parallel collection mechanisms and
thread safety of concurrent operations.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestThreadPoolExecutorBehavior:
    """Test ThreadPoolExecutor behavior patterns used in collectors"""

    def test_threadpool_collects_all_results(self):
        """Test that ThreadPoolExecutor collects all results correctly"""

        def task(n):
            time.sleep(0.01)  # Simulate work
            return n * 2

        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(task, i): i for i in range(10)}

            for future in as_completed(futures):
                results.append(future.result())

        # All 10 tasks should complete
        assert len(results) == 10
        # Results should be correct
        assert sorted(results) == [i * 2 for i in range(10)]

    def test_threadpool_handles_exceptions_gracefully(self):
        """Test that ThreadPoolExecutor handles task exceptions without killing other tasks"""

        def task_with_conditional_error(n):
            if n == 5:
                raise ValueError(f"Task {n} failed")
            return n * 2

        results = []
        errors = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(task_with_conditional_error, i): i for i in range(10)}

            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    errors.append(str(e))

        # 9 successful tasks and 1 error
        assert len(results) == 9
        assert len(errors) == 1
        assert "Task 5 failed" in errors[0]

    def test_threadpool_respects_max_workers(self):
        """Test that ThreadPoolExecutor limits concurrent execution"""
        active_tasks = []
        max_concurrent = 0

        def task_that_tracks_concurrency(n):
            active_tasks.append(n)
            nonlocal max_concurrent
            max_concurrent = max(max_concurrent, len(active_tasks))
            time.sleep(0.05)  # Simulate work
            active_tasks.remove(n)
            return n

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(task_that_tracks_concurrency, i) for i in range(10)]
            for future in futures:
                future.result()

        # Should never exceed 3 concurrent tasks
        assert max_concurrent <= 3
        # Should have used multiple workers (not serial)
        assert max_concurrent >= 2

    def test_parallel_execution_faster_than_serial(self):
        """Test that parallel execution provides speedup"""

        def task(n):
            time.sleep(0.05)
            return n

        # Parallel execution
        start_parallel = time.time()
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(task, i) for i in range(10)]
            for future in futures:
                future.result()
        parallel_time = time.time() - start_parallel

        # Serial execution
        start_serial = time.time()
        for i in range(10):
            task(i)
        serial_time = time.time() - start_serial

        # Parallel should be at least 2x faster
        assert parallel_time < serial_time * 0.6


class TestConcurrentDataAggregation:
    """Test patterns for aggregating data from concurrent tasks"""

    def test_list_append_in_threads_thread_safe(self):
        """Test that appending to list from multiple threads is safe with GIL"""
        results = []

        def append_items(start, count):
            for i in range(start, start + count):
                results.append(i)
                time.sleep(0.001)  # Simulate some work

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(append_items, 0, 10),
                executor.submit(append_items, 10, 10),
                executor.submit(append_items, 20, 10),
                executor.submit(append_items, 30, 10),
            ]
            for future in futures:
                future.result()

        # All 40 items should be present (no lost updates)
        assert len(results) == 40
        # All items should be unique
        assert len(set(results)) == 40

    def test_dict_merge_pattern(self):
        """Test pattern of merging results from parallel tasks into dict"""

        def collect_data(key):
            time.sleep(0.01)
            return key, {"count": key * 10, "items": [f"item_{i}" for i in range(key)]}

        results = {}

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(collect_data, i): i for i in range(5)}

            for future in as_completed(futures):
                key, data = future.result()
                results[key] = data

        # All keys should be present
        assert len(results) == 5
        # Data should be correct
        for i in range(5):
            assert results[i]["count"] == i * 10
            assert len(results[i]["items"]) == i

    def test_collect_with_status_tracking(self):
        """Test pattern of tracking success/failure during collection"""

        def task_with_occasional_failure(n):
            if n % 3 == 0 and n > 0:
                raise Exception(f"Task {n} failed")
            return {"task_id": n, "data": n * 2}

        successful = []
        failed = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(task_with_occasional_failure, i): i for i in range(10)}

            for future, task_id in futures.items():
                try:
                    result = future.result()
                    successful.append(result)
                except Exception as e:
                    failed.append({"task_id": task_id, "error": str(e)})

        # Should have 7 successful and 3 failed
        assert len(successful) == 7
        assert len(failed) == 3
        # Failed tasks should be 3, 6, 9
        failed_ids = sorted([f["task_id"] for f in failed])
        assert failed_ids == [3, 6, 9]


class TestAsCompletedPattern:
    """Test as_completed() pattern used in collectors"""

    def test_as_completed_processes_fastest_first(self):
        """Test that as_completed yields results as they finish"""

        def task_with_variable_time(n):
            # Some tasks are fast, some are slow
            sleep_time = 0.001 if n < 3 else 0.1
            time.sleep(sleep_time)
            return n

        completion_order = []

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(task_with_variable_time, i): i for i in range(6)}

            for future in as_completed(futures):
                result = future.result()
                completion_order.append(result)

        # Fast tasks (0, 1, 2) should complete before slow tasks (3, 4, 5)
        # Check that at least 2 of the first 3 completed are fast tasks
        fast_in_first_three = sum(1 for x in completion_order[:3] if x < 3)
        assert fast_in_first_three >= 2

    def test_as_completed_with_timeout(self):
        """Test as_completed with timeout handling"""

        def task_with_variable_speed(n):
            # Tasks 0, 1 are fast, 2,3,4 are slow
            time.sleep(0.01 if n < 2 else 0.5)
            return n

        completed = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(task_with_variable_speed, i): i for i in range(5)}

            # Wait for all futures with a reasonable timeout
            try:
                for future in as_completed(futures, timeout=1.5):
                    try:
                        result = future.result()
                        completed.append(result)
                    except Exception:
                        pass
            except TimeoutError:
                # Some tasks may timeout, which is fine for this test
                pass

        # Fast tasks should complete (at least tasks 0 and 1)
        assert len(completed) >= 2
        # Fast tasks should be in completed
        assert 0 in completed or 1 in completed


class TestErrorRecoveryPatterns:
    """Test error recovery patterns in parallel collection"""

    def test_continue_on_partial_failure(self):
        """Test collection continues when some tasks fail"""

        def flaky_task(n):
            if n in [2, 5, 7]:
                raise RuntimeError(f"Simulated failure for task {n}")
            return n * 10

        results = {}
        errors = {}

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(flaky_task, i): i for i in range(10)}

            for future, task_id in futures.items():
                try:
                    results[task_id] = future.result()
                except Exception as e:
                    errors[task_id] = str(e)

        # Should have 7 successes and 3 failures
        assert len(results) == 7
        assert len(errors) == 3
        assert 2 in errors and 5 in errors and 7 in errors

    def test_retry_pattern_for_failed_tasks(self):
        """Test pattern of retrying failed tasks"""
        attempt_count = {}

        def task_that_needs_retry(n):
            attempts = attempt_count.get(n, 0) + 1
            attempt_count[n] = attempts

            if attempts < 2:
                raise RuntimeError(f"Task {n} not ready (attempt {attempts})")
            return n * 10

        results = {}
        max_retries = 2

        with ThreadPoolExecutor(max_workers=3) as executor:
            # First attempt
            futures = {executor.submit(task_that_needs_retry, i): i for i in range(5)}
            retry_tasks = []

            for future, task_id in futures.items():
                try:
                    results[task_id] = future.result()
                except Exception:
                    retry_tasks.append(task_id)

            # Retry failed tasks
            if retry_tasks:
                retry_futures = {executor.submit(task_that_needs_retry, i): i for i in retry_tasks}

                for future, task_id in retry_futures.items():
                    try:
                        results[task_id] = future.result()
                    except Exception:
                        pass  # Give up after retry

        # All tasks should eventually succeed after retry
        assert len(results) == 5


class TestDataConsistencyInParallelCollection:
    """Test data consistency when collecting from multiple sources concurrently"""

    def test_no_duplicate_data_from_concurrent_collection(self):
        """Test that concurrent collection doesn't create duplicates"""

        def collect_from_source(source_id):
            # Each source returns unique items
            return [{"id": f"{source_id}_{i}", "value": i} for i in range(10)]

        all_items = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(collect_from_source, i) for i in range(5)]

            for future in futures:
                items = future.result()
                all_items.extend(items)

        # Should have 50 unique items (5 sources × 10 items)
        assert len(all_items) == 50
        item_ids = [item["id"] for item in all_items]
        assert len(set(item_ids)) == 50  # All unique

    def test_aggregation_preserves_data_integrity(self):
        """Test that aggregating concurrent results preserves data integrity"""

        def collect_metrics(team_id):
            return {
                "team_id": team_id,
                "members": 5,
                "prs": team_id * 10,
                "commits": team_id * 20,
                "checksum": (team_id * 10) + (team_id * 20),  # For validation
            }

        results = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(collect_metrics, i) for i in range(8)]

            for future in futures:
                results.append(future.result())

        # Verify all data is consistent
        for team_data in results:
            expected_checksum = team_data["prs"] + team_data["commits"]
            assert team_data["checksum"] == expected_checksum

        # Verify no data loss
        assert len(results) == 8
        team_ids = [r["team_id"] for r in results]
        assert sorted(team_ids) == list(range(8))
