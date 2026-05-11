import asyncio
import random
from typing import Optional, Dict, Any, List

from langchain_core.tools import BaseTool


class RetryableError(Exception):
    pass


class NonRetryableError(Exception):
    pass


_NON_RETRYABLE_TYPES = (ValueError, KeyError, TypeError)
_NON_RETRYABLE_KEYWORDS = [
    "400", "401", "403", "404",
    "authentication", "invalid api key", "invalid x-api-key",
    "model not found", "context length",
]


def _is_retryable(e: Exception) -> bool:
    if isinstance(e, NonRetryableError):
        return False
    if isinstance(e, RetryableError):
        return True
    if isinstance(e, _NON_RETRYABLE_TYPES):
        return False
    msg = str(e).lower()
    return not any(kw in msg for kw in _NON_RETRYABLE_KEYWORDS)


async def _invoke_tool_with_retry(
    tool: BaseTool,
    arguments: Dict[str, Any],
    max_retries: int = 3,
    per_attempt_timeout: float = 30.0,
) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                tool.ainvoke(arguments), timeout=per_attempt_timeout
            )
            return result
        except asyncio.TimeoutError:
            last_error = RetryableError(
                f"Tool {tool.name} timed out after {per_attempt_timeout}s"
            )
            print(
                f"⚠️ 工具调用超时 [{tool.name}] "
                f"(尝试 {attempt + 1}/{max_retries})"
            )
        except Exception as e:
            if not _is_retryable(e):
                raise NonRetryableError(
                    f"Non-retryable error in {tool.name}: {e}"
                ) from e
            last_error = e
            error_name = type(e).__name__
            print(
                f"⚠️ 工具调用失败 [{tool.name}] "
                f"(尝试 {attempt + 1}/{max_retries}): "
                f"{error_name}: {str(e)[:100]}"
            )

        if attempt < max_retries - 1:
            base_wait = min(2 ** attempt, 15)
            jitter = random.uniform(0, 2)
            wait_time = base_wait + jitter
            print(f"   等待 {wait_time:.1f} 秒后重试...")
            await asyncio.sleep(wait_time)
        else:
            print(
                f"❌ 工具调用最终失败 [{tool.name}] "
                f"(已重试 {max_retries} 次)"
            )

    raise last_error  # type: ignore[misc]


async def _invoke_llm_with_retry(
    llm_with_tools,
    messages: list,
    max_retries: int = 3,
    per_attempt_timeout: float = 120.0,
) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                llm_with_tools.ainvoke(messages), timeout=per_attempt_timeout
            )
            return result
        except asyncio.TimeoutError:
            last_error = RetryableError(
                f"LLM call timed out after {per_attempt_timeout}s"
            )
            print(
                f"⚠️ LLM调用超时 "
                f"(尝试 {attempt + 1}/{max_retries})"
            )
        except Exception as e:
            if not _is_retryable(e):
                raise NonRetryableError(
                    f"Non-retryable LLM error: {e}"
                ) from e
            last_error = e
            error_name = type(e).__name__
            print(
                f"⚠️ LLM调用失败 "
                f"(尝试 {attempt + 1}/{max_retries}): "
                f"{error_name}: {str(e)[:100]}"
            )

        if attempt < max_retries - 1:
            base_wait = min(2 ** attempt, 15)
            jitter = random.uniform(0, 2)
            wait_time = base_wait + jitter
            print(f"   等待 {wait_time:.1f} 秒后重试...")
            await asyncio.sleep(wait_time)
        else:
            print(
                f"❌ LLM调用最终失败 "
                f"(已重试 {max_retries} 次)"
            )

    raise last_error  # type: ignore[misc]
