"""LLM服务模块 (LangChain / LangGraph 兼容版本)"""

import os
import threading
import json
import re
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from ..config import get_settings

_llm_instance: Optional[BaseChatModel] = None
_llm_lock = threading.Lock()

def get_llm() -> BaseChatModel:
    """
    获取线程安全单例模式的LangChain ChatModel实例。

    Returns:
        BaseChatModel: 兼容LangGraph节点调用的模型实例。
    """
    global _llm_instance

    if _llm_instance is not None:
        return _llm_instance

    with _llm_lock:
        if _llm_instance is not None:
            return _llm_instance

        settings = get_settings()

        api_key = settings.llm_api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        base_url = settings.llm_base_url or settings.openai_base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
        model_name = settings.llm_model_name or settings.openai_model or os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL_ID") or "gpt-4o"

        if not api_key:
            raise ValueError("未能获取到 LLM_API_KEY，请检查环境变量或配置文件。")

        _llm_instance = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.2,
            request_timeout=120,
            max_retries=0,
            max_tokens=8192,
            extra_body=(
                {"thinking": {"type": settings.llm_thinking_mode}}
                if model_name.lower().startswith("deepseek-v4") or model_name.lower() == "deepseek-flash"
                else None
            ),
        )

        print(f"✅ LangChain LLM服务初始化成功")
        print("   基础URL: 已配置" if base_url else "   基础URL: 默认 OpenAI 节点")
        print(f"   模型名称: {model_name}")

    return _llm_instance

_structured_capability: Optional[bool] = None


def is_structured_output_supported() -> bool:
    return get_settings().llm_structured_output_mode != 'json_prompt' and _structured_capability is not False


async def invoke_structured_or_json(llm, messages, schema, *, timeout=60):
    from .external_calls import ExternalServiceError, FailureKind
    try:
        return await _invoke_structured_or_json(llm, messages, schema, timeout=timeout)
    except TimeoutError:
        raise ExternalServiceError('llm', 'structured_output', FailureKind.TIMEOUT) from None


async def _invoke_structured_or_json(llm, messages, schema, *, timeout=60):
    """The first requested structured call probes support; fallback shares its deadline."""
    global _structured_capability
    from .external_calls import invoke_llm, ExternalServiceError, FailureKind, operation_deadline
    async with operation_deadline(min(timeout, get_settings().external_llm_timeout)):
        if is_structured_output_supported():
            try:
                result = await invoke_llm(llm.with_structured_output(schema, method='function_calling'),
                                          messages, max_attempts=1, timeout=timeout)
                _structured_capability = True
                return result
            except (ValueError, NotImplementedError):
                _structured_capability = False
            except ExternalServiceError as error:
                # Authentication, outages and timeouts are not capability probes.
                if error.kind != FailureKind.INVALID_REQUEST:
                    raise
                _structured_capability = False
        result = await invoke_llm(llm, messages, max_attempts=1, timeout=timeout)
        text = result.content if hasattr(result, 'content') else str(result)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            raise ExternalServiceError('llm', 'json_parse', FailureKind.INVALID_RESPONSE)
        try:
            return schema.model_validate(json.loads(match.group()))
        except (ValueError, TypeError):
            raise ExternalServiceError('llm', 'json_parse', FailureKind.INVALID_RESPONSE) from None


def reset_llm():
    """重置LLM实例(用于测试或重新配置)"""
    global _llm_instance, _structured_capability
    _llm_instance = None
    _structured_capability = None


async def close_llm():
    global _llm_instance
    instance = _llm_instance
    reset_llm()
    if instance is not None:
        client = getattr(instance, 'root_async_client', None)
        if client:
            await client.close()
        client = getattr(instance, 'root_client', None)
        if client:
            client.close()
