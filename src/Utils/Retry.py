import logging
import time
import typing

T = typing.TypeVar("T")


def WithRetry(fn: typing.Callable[[], T], max_attempts: int = 3, base_delay_s: float = 2.0) -> T:
    """Calls fn(), retrying on any exception with exponential backoff (base_delay_s,
    2*base_delay_s, 4*base_delay_s, ...). Re-raises the last exception once max_attempts
    is exhausted. Used to ride out transient network errors / rate limiting on calls to
    third-party sites (e.g. Baseball-Reference via pybaseball)."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts:
                raise
            delay = base_delay_s * (2 ** (attempt - 1))
            logging.warning(f"Attempt {attempt}/{max_attempts} failed ({e}); retrying in {delay:.1f}s")
            time.sleep(delay)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    calls = {"count": 0}

    def _flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("transient failure")
        return "ok"

    result = WithRetry(_flaky, max_attempts=3, base_delay_s=0.01)
    assert result == "ok"
    assert calls["count"] == 3

    def _always_fails() -> str:
        raise RuntimeError("permanent failure")

    try:
        WithRetry(_always_fails, max_attempts=2, base_delay_s=0.01)
        raise AssertionError("expected RuntimeError to propagate after exhausting attempts")
    except RuntimeError as e:
        assert str(e) == "permanent failure"

    print("Retry self-checks passed.")
