"""Compatibility helpers; retry and timeout ownership lives in external_calls."""
from ...services.external_calls import (CallPolicy, ExternalServiceError, classify_error,
    FailureKind, invoke_external, invoke_llm, decode_tool_result)
from ...services.mcp_gateway import ManagedMCPTool


class RetryableError(Exception):
    pass


class NonRetryableError(Exception):
    pass


def _is_retryable(error):
    return isinstance(error, RetryableError) or classify_error(error) in {
        FailureKind.TIMEOUT, FailureKind.CONNECTION, FailureKind.RATE_LIMIT, FailureKind.UNAVAILABLE}


async def _invoke_tool_with_retry(tool, arguments, max_retries=2, per_attempt_timeout=30.0):
    if isinstance(tool, ManagedMCPTool):
        return await tool.invoke_bounded(arguments, timeout=per_attempt_timeout, max_attempts=max_retries)
    name = getattr(tool, 'name', None)
    name = name if isinstance(name, str) else 'tool'
    async def invoke():
        return decode_tool_result(await tool.ainvoke(arguments), 'mcp', name)
    return await invoke_external('mcp', name, invoke,
        policy=CallPolicy(total_timeout=per_attempt_timeout, attempt_timeout=min(20, per_attempt_timeout),
                          max_attempts=min(max_retries, 2)))


async def _invoke_llm_with_retry(llm_with_tools, messages, max_retries=2, per_attempt_timeout=60.0):
    return await invoke_llm(llm_with_tools, messages, max_attempts=max_retries, timeout=per_attempt_timeout)
