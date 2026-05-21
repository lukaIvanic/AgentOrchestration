import asyncio
import time

import pytest

from src.sdk.decorators import task


def test_task_decorator_supports_sync_functions():
    @task(name="sync-add", timeout=1)
    def sync_add(left, right):
        return left + right

    result = asyncio.run(sync_add(2, 3))

    assert result == 5
    assert sync_add.__task_config__ == {
        "name": "sync-add",
        "retries": 0,
        "timeout": 1,
    }


def test_task_decorator_supports_sync_kwargs():
    @task(timeout=1)
    def sync_format(prefix, *, value):
        return f"{prefix}:{value}"

    result = asyncio.run(sync_format("item", value=7))

    assert result == "item:7"


def test_task_decorator_preserves_async_functions():
    @task(timeout=1)
    async def async_add(left, right):
        await asyncio.sleep(0)
        return left + right

    result = asyncio.run(async_add(2, 3))

    assert result == 5
    assert async_add.__task_config__["name"] == "async_add"


def test_task_decorator_times_out_sync_functions_cleanly():
    @task(name="slow-sync", timeout=0.01)
    def slow_sync():
        time.sleep(0.05)

    with pytest.raises(TimeoutError, match="slow-sync.*timed out"):
        asyncio.run(slow_sync())


def test_task_decorator_preserves_sync_exceptions():
    @task(timeout=1)
    def sync_fail():
        raise ValueError("handler failed")

    with pytest.raises(ValueError, match="handler failed"):
        asyncio.run(sync_fail())
