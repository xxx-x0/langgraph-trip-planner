"""从旅游攻略文本提取景点名，并模糊匹配到当前景点池。"""

import json
import logging
import re
from typing import Any, Dict, List

from ....services.llm_service import get_llm, is_structured_output_supported


logger = logging.getLogger(__name__)


# 按长度降序，确保更长的后缀优先匹配
# 例：「九寨沟风景区」应被 "风景区" 而非 "景区" 剥离
SUFFIXES = sorted([
    "风景名胜区",
    "自然保护区",
    "森林公园",
    "度假区",
    "风景区",
    "博物院",
    "博物馆",
    "动物园",
    "植物园",
    "景区",
    "公园",
    "广场",
    "园林",
    "胜地",
    "古镇",
], key=len, reverse=True)

# Prompt 输入截断阈值（字符）：5 个 snippet × 500 字符 = 2500 上限，
# 4000 留出 LLM 思考的 prompt 头/尾空间，对 DeepSeek 32K 上下文绰绰有余
_MAX_PROMPT_CHARS = 4000


def normalize_name(name: str) -> str:
    """去除常见景点后缀，便于模糊匹配。

    注意：只删除明确的景点后缀，避免误删如"北京大学"中的"学"。
    """
    n = (name or "").strip()
    for suf in SUFFIXES:
        if n.endswith(suf) and len(n) > len(suf):
            n = n[: -len(suf)]
            break
    return n


def match_names_to_pool(
    candidate_names: List[str],
    pool: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """把 LLM 提取出的景点名匹配到 pool 中的景点。

    匹配规则（按优先级）：
    1. normalize 后完全相等（处理短名如 "故宫"）
    2. cand 与 item_name 双向包含，但要求两侧 normalize 长度 >= 3，
       避免 "故宫" 误匹配 "故宫小学"、"北京" 误匹配 "北京大学"。
       注意：2 字符短名（"故宫"/"天坛"）只能通过规则 1 精确匹配，
       不允许作为子串模糊匹配，因为它们极易嵌入到非景点名字中。
    """
    if not candidate_names or not pool:
        return []
    matched: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for cand in candidate_names:
        cand_norm = normalize_name(cand)
        if not cand_norm:
            continue
        for item in pool:
            item_id = item.get("poi_id") or item.get("name")
            if item_id in seen_ids:
                continue
            item_name = item.get("name", "") or ""
            item_norm = normalize_name(item_name)
            if not item_norm:
                continue
            # 规则 1: normalize 后完全相等
            if cand_norm == item_norm:
                matched.append(item)
                seen_ids.add(item_id)
                break
            # 规则 2: 双向部分包含，要求 normalize 后两侧 >= 3 字符
            if len(cand_norm) < 3 or len(item_norm) < 3:
                continue
            if cand_norm in item_norm or item_norm in cand_norm:
                matched.append(item)
                seen_ids.add(item_id)
                break
    return matched


async def _bing_search_snippets(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """调用 Bing MCP 搜索，返回 [{title, snippet}, ...]。

    若 Bing 服务未配置或调用失败，返回空列表。
    """
    from ....services.bing_mcp_service import get_bing_service

    service = get_bing_service()
    if service is None:
        return []
    raw = await service.search(query, count=top_k, offset=0)

    # raw 可能是 string / list / dict，统一规范化
    items: List[Dict[str, Any]] = []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return [{"title": "", "snippet": raw[:2000]}]
        raw = parsed

    if isinstance(raw, dict):
        # 常见结构：{"results": [...]} 或 {"webPages": {"value": [...]}}
        candidates = (
            raw.get("results")
            or raw.get("data")
            or (raw.get("webPages") or {}).get("value")
            or []
        )
        raw = candidates

    if isinstance(raw, list):
        for r in raw[:top_k]:
            if isinstance(r, dict):
                title = r.get("title") or r.get("name") or ""
                snippet = (
                    r.get("snippet")
                    or r.get("description")
                    or r.get("summary")
                    or r.get("content")
                    or ""
                )
                items.append({"title": str(title), "snippet": str(snippet)})
            elif isinstance(r, str):
                items.append({"title": "", "snippet": r})

    return items


async def extract_attractions_from_strategy(
    destination: str,
    days: int,
    pool: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """调 Bing 搜索 + LLM 解析，返回 {recommended_ids, source_strategy_title}。"""

    query = f"{destination} {days}日游 经典攻略"
    try:
        results = await _bing_search_snippets(query, top_k=5)
    except Exception:
        logger.exception("Bing search failed for strategy extraction")
        return {"recommended_ids": [], "source_strategy_title": None}

    combined = "\n\n".join(
        f"标题：{r.get('title', '')}\n摘要：{(r.get('snippet', '') or '')[:500]}"
        for r in (results or [])[:5]
    )
    if not combined.strip():
        return {"recommended_ids": [], "source_strategy_title": None}

    prompt = f"""从下面的旅游攻略文本中提取在 {destination} 出现的所有具体景点名（不要市/区/省/餐厅/酒店）。

输出 JSON：{{"attractions": ["景点1", "景点2", ...]}}

攻略文本：
{combined[:_MAX_PROMPT_CHARS]}"""

    try:
        llm = get_llm()
        if is_structured_output_supported():
            from pydantic import BaseModel
            from typing import List as _L

            class _Out(BaseModel):
                attractions: _L[str]

            structured_llm = llm.with_structured_output(_Out, method="function_calling")
            resp = await structured_llm.ainvoke(prompt)
            names = list(resp.attractions or [])
        else:
            raw = await llm.ainvoke(prompt)
            text = raw.content if hasattr(raw, "content") else str(raw)
            m = re.search(r"\{.*\}", text, re.DOTALL)
            names = json.loads(m.group(0)).get("attractions", []) if m else []
    except Exception:
        logger.exception("LLM strategy extraction failed")
        return {"recommended_ids": [], "source_strategy_title": None}

    matched = match_names_to_pool(names, pool)
    recommended_ids = [m.get("poi_id") for m in matched if m.get("poi_id")]
    source_title = results[0].get("title") if results else None
    return {
        "recommended_ids": recommended_ids,
        "source_strategy_title": source_title,
    }
