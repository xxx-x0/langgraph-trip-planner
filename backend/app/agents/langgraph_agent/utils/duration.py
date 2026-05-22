"""景点游玩时长估算工具。

使用 LLM 一次性估算所有候选景点的游玩时长；失败时使用 CATEGORY_DURATION_MAP 降级。
"""
import asyncio
from typing import Dict, List

from langchain_core.messages import HumanMessage

from ..exceptions import _invoke_llm_with_retry
from .parsing import _extract_json_array
from ....services.llm_service import get_llm


CATEGORY_DURATION_MAP: Dict[str, int] = {
    "博物馆": 120,
    "公园": 60,
    "寺庙": 90,
    "古迹": 75,
    "美食": 45,
    "购物": 90,
    "自然风光": 120,
    "历史文化": 90,
    "亲子": 90,
    "景点": 90,
    "default": 90,
}

MIN_MINUTES = 15
MAX_MINUTES = 480


def _fallback_durations(attractions: List[Dict]) -> Dict[str, int]:
    """根据 category 映射给每个景点分配默认时长。"""
    result: Dict[str, int] = {}
    for attr in attractions:
        name = attr.get("name", "")
        if not name:
            continue
        category = attr.get("category") or "default"
        result[name] = CATEGORY_DURATION_MAP.get(category, CATEGORY_DURATION_MAP["default"])
    return result


async def estimate_durations_batch(
    attractions: List[Dict],
    timeout_seconds: float = 8.0,
) -> Dict[str, int]:
    """一次性估算所有景点的游玩时长（分钟）。

    Args:
        attractions: 每项含 name / description / category 字段
        timeout_seconds: LLM 调用超时

    Returns:
        {name: minutes}，失败/缺失项用 CATEGORY_DURATION_MAP 兜底
    """
    if not attractions:
        return {}

    fallback = _fallback_durations(attractions)

    lines = []
    for i, attr in enumerate(attractions):
        name = attr.get("name", f"景点{i}")
        category = attr.get("category", "")
        description = (attr.get("description") or "").strip()[:120]
        lines.append(f"- 名称: {name} | 类别: {category} | 简介: {description}")
    attractions_text = "\n".join(lines)

    prompt = f"""请根据下列景点的名称、类别、简介，估算每个景点的合理游玩时长（分钟）。
要求严格输出 JSON 数组，每项包含 name 与 visit_minutes（15~480 的整数），不要输出额外文字。

景点列表：
{attractions_text}

示例输出：
[{{"name":"故宫博物院","visit_minutes":180}},{{"name":"景山公园","visit_minutes":60}}]
"""

    try:
        llm = get_llm()
        response = await asyncio.wait_for(
            _invoke_llm_with_retry(llm, [HumanMessage(content=prompt)], max_retries=2),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        print(f"⚠️ 游玩时长估算超时（>{timeout_seconds}s），使用默认值兜底")
        return fallback
    except Exception as e:
        print(f"⚠️ 游玩时长估算失败（{type(e).__name__}）: {e}，使用默认值兜底")
        return fallback

    parsed = _extract_json_array(response.content)
    if not parsed:
        print("⚠️ 游玩时长估算返回无法解析，使用默认值兜底")
        return fallback

    result: Dict[str, int] = {}
    for item in parsed:
        name = item.get("name")
        minutes = item.get("visit_minutes")
        if not name:
            continue
        try:
            minutes_int = int(minutes)
        except (TypeError, ValueError):
            continue
        if MIN_MINUTES <= minutes_int <= MAX_MINUTES:
            result[name] = minutes_int

    # 缺失项用 fallback 补齐
    for name, default_min in fallback.items():
        result.setdefault(name, default_min)

    return result
