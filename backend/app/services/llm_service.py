"""LLM服务模块 (LangChain / LangGraph 兼容版本)"""

import os
import threading
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
            max_retries=2,
            max_tokens=8192,
        )

        print(f"✅ LangChain LLM服务初始化成功")
        print(f"   基础URL: {base_url or '默认 OpenAI 节点'}")
        print(f"   模型名称: {model_name}")

    return _llm_instance

_STRUCTURED_OUTPUT_UNSUPPORTED_PATTERNS = [
    "deepseek",
    "qwen",
    "doubao",
    "yi",
    "zhipu",
    "glm",
    "moonshot",
    "minimax",
    "baichuan",
]


def is_structured_output_supported() -> bool:
    global _llm_instance
    if _llm_instance is None:
        get_llm()
    model_name = (_llm_instance.model_name or "").lower()
    base_url = ""
    if hasattr(_llm_instance, 'openai_api_base') and _llm_instance.openai_api_base:
        base_url = _llm_instance.openai_api_base.lower()
    elif hasattr(_llm_instance, 'base_url') and _llm_instance.base_url:
        base_url = str(_llm_instance.base_url).lower()
    combined = model_name + " " + base_url
    for pattern in _STRUCTURED_OUTPUT_UNSUPPORTED_PATTERNS:
        if pattern in combined:
            return False
    return True


def reset_llm():
    """重置LLM实例(用于测试或重新配置)"""
    global _llm_instance
    _llm_instance = None

    
# """LLM服务模块"""

# from hello_agents import HelloAgentsLLM
# from ..config import get_settings

# # 全局LLM实例
# _llm_instance = None


# def get_llm() -> HelloAgentsLLM:
#     """
#     获取LLM实例(单例模式)
    
#     Returns:
#         HelloAgentsLLM实例
#     """
#     global _llm_instance
    
#     if _llm_instance is None:
#         settings = get_settings()
        
#         # HelloAgentsLLM会自动从环境变量读取配置
#         # 包括OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL等
#         _llm_instance = HelloAgentsLLM()
        
#         print(f"✅ LLM服务初始化成功")
#         print(f"   提供商: {_llm_instance.provider}")
#         print(f"   模型: {_llm_instance.model}")
    
#     return _llm_instance


# def reset_llm():
#     """重置LLM实例(用于测试或重新配置)"""
#     global _llm_instance
#     _llm_instance = None

