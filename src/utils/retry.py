"""Retry utilities with exponential backoff."""

import time
from functools import wraps
from typing import Any, Callable, TypeVar

from jira.exceptions import JIRAError


# Type variable for generic function signatures
F = TypeVar("F", bound=Callable[..., Any])


def exponential_backoff_retry(
    max_retries: int = 3,
    delays: list[int] | None = None,
) -> Callable[[F], F]:
    """Decorator for exponential backoff retry (2s, 4s, 8s).

    Retries on Jira rate limits (429) and transient server errors (5xx).
    Per research.md section 2, uses explicit delays of 2s, 4s, 8s.

    Args:
        max_retries: Maximum number of retry attempts (default: 3).
        delays: List of delay seconds between retries (default: [2, 4, 8]).

    Returns:
        Callable: Decorated function with retry logic.

    Examples:
        >>> @exponential_backoff_retry()
        ... def call_jira_api():
        ...     # Jira API call here
        ...     pass
    """
    if delays is None:
        delays = [2, 4, 8]

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except JIRAError as e:
                    # Retry on rate limit (429) or server errors (5xx)
                    if e.status_code in (429, 500, 502, 503, 504):
                        if attempt < max_retries:
                            delay = delays[attempt]
                            print(
                                f"Jira error {e.status_code}, retrying in {delay}s..."
                            )
                            time.sleep(delay)
                            continue
                    # Non-retryable error or retries exhausted
                    raise
            raise Exception(
                f"Max retries ({max_retries}) exhausted for {func.__name__}"
            )

        return wrapper  # type: ignore

    return decorator
