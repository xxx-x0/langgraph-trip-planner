"""从旅游攻略文本提取景点名，并模糊匹配到当前景点池。"""

import json
import logging
import re
from typing import Any, Dict, List

from ....services.llm_service import get_llm, is_structured_output_supported


logger = logging.getLogger(__name__)


SUFFIXES = ["博物院", "博物馆", "景区", "公园", "广场", "园林", "胜地", "古镇"]


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

    匹配规则：原名包含、normalize 后包含、双向 in。
    防重复：同一个 pool 项最多被匹配一次。
    """
    if not candidate_names or not pool:
        return []
    matched: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for cand in candidate_names:
        if not cand:
            continue
        cand_norm = normalize_name(cand)
        for item in pool:
            item_id = item.get("poi_id") or item.get("name")
            if item_id in seen_ids:
                continue
            item_name = item.get("name", "") or ""
            item_norm = normalize_name(item_name)
            if not item_name:
                continue
            if (
                cand in item_name
                or item_name in cand
                or (cand_norm and item_norm and (cand_norm in item_norm or item_norm in cand_norm))
            ):
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
{combined[:4000]}"""

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
    return {
        "recommended_ids": [m.get("poi_id") or m.get("name") for m in matched],
        "source_strategy_title": (results or [{}])[0].get("title") or None,
    }
