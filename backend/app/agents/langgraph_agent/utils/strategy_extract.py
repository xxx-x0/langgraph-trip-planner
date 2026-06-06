"""从旅游攻略文本提取景点名，并模糊匹配到当前景点池。"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

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


# ============================================================================
# v2: 池内 LLM 挑选（替代攻略提取）
# ============================================================================

from .duration import estimate_durations_batch


def _parse_rating(value: Any) -> float:
    """解析 rating 字段，失败返回 0"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _rating_based_fallback(
    pool: List[Dict[str, Any]],
    days: int,
) -> Tuple[List[str], List[str]]:
    """按 rating 降序兜底分配 must 和 optional。

    must = top days * 3，optional = next days * 2。
    缺 poi_id 的景点被跳过。
    """
    # 仅保留有 poi_id 的
    valid = [p for p in pool if p.get("poi_id")]
    sorted_pool = sorted(
        valid,
        key=lambda p: _parse_rating(p.get("rating")),
        reverse=True,
    )
    must_count = days * 3
    optional_count = days * 2
    must_ids = [p["poi_id"] for p in sorted_pool[:must_count]]
    optional_ids = [p["poi_id"] for p in sorted_pool[must_count:must_count + optional_count]]
    return must_ids, optional_ids


def _format_preferences(preferences: Optional[Any]) -> str:
    if not preferences:
        return "无特别偏好"
    if isinstance(preferences, dict):
        parts = []
        label_map = {
            "interests": "兴趣类型",
            "preferences": "兴趣类型",
            "food_preference": "美食偏好",
            "free_text_input": "额外要求",
            "transportation": "交通方式",
            "accommodation": "住宿偏好",
            "budget": "预算",
            "companions": "同伴",
        }
        for key, label in label_map.items():
            value = preferences.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                value_text = "、".join(str(v) for v in value)
            else:
                value_text = str(value)
            parts.append(f"{label}: {value_text}")
        return "；".join(parts) if parts else json.dumps(preferences, ensure_ascii=False)
    if isinstance(preferences, list):
        return "、".join(str(p) for p in preferences)
    return str(preferences)


def _collect_explanations(
    items: List[Dict[str, Any]],
    valid_ids: set[str],
) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    reasons: Dict[str, str] = {}
    tags: Dict[str, List[str]] = {}
    for item in items:
        poi_id = item.get("poi_id")
        if not poi_id or poi_id not in valid_ids:
            continue
        reason = item.get("reason")
        if reason:
            reasons[poi_id] = str(reason)
        raw_tags = item.get("tags") or []
        if isinstance(raw_tags, list):
            tags[poi_id] = [str(tag) for tag in raw_tags if str(tag).strip()][:4]
    return reasons, tags


def _short_text(value: Any, limit: int = 80) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text[:limit]


async def pick_attractions_from_pool(
    destination: str,
    days: int,
    pool: List[Dict[str, Any]],
    preferences: Optional[Any] = None,
) -> Dict[str, Any]:
    """从景点池中挑选推荐项，返回 ids 和解释信息。

    流程：
    1. estimate_durations_batch 估时（失败默认 120）
    2. LLM 选 must / optional（时长预算 + 用户偏好驱动）
    3. LLM 失败 / 无效输出 → rating 兜底
    """
    if not pool:
        return {"must_ids": [], "optional_ids": []}

    # Step 1: 估时（失败时默认 120）
    try:
        durations = await estimate_durations_batch(pool)
    except Exception:
        logger.exception("estimate_durations_batch failed; default to 120 min")
        durations = {p.get("name", ""): 120 for p in pool}

    # Step 2: LLM 选
    must_target = days * 360  # 6h/天
    optional_target = days * 120  # 2h/天

    pool_lines = []
    for p in pool:
        poi_id = p.get("poi_id")
        if not poi_id:
            continue
        name = p.get("name", "")
        category = p.get("category", "")
        rating = p.get("rating", "")
        address = _short_text(p.get("address"), 60)
        description = _short_text(p.get("description"), 90)
        open_hours = _short_text(p.get("open_hours"), 50)
        ticket_price = p.get("ticket_price", "")
        dur = durations.get(name, 120)
        pool_lines.append(
            f"{poi_id} | {name} | 类别:{category} | 评分:{rating} | "
            f"时长:{dur}min | 地址:{address} | 开放:{open_hours} | "
            f"门票:{ticket_price} | 简介:{description}"
        )

    prefs_str = _format_preferences(preferences)
    prompt = f"""你是行程规划助手。请从下面这个 {destination} 的景点池里，
为一个 {days} 天的行程挑选必去和备选景点。

行程目标：
- 必去景点（must）：总游览时长约 {must_target} 分钟（6 小时/天）
- 备选景点（optional）：额外约 {optional_target} 分钟（2 小时/天）

用户偏好：{prefs_str}

景点池（poi_id | 名称 | 类别 | 评分 | 预估时长 | 地址 | 开放时间 | 门票 | 简介）：
{chr(10).join(pool_lines)}

仅输出 JSON，格式：
{{"summary": "一句话说明选择策略", "must": [{{"poi_id": "xxx", "reason": "...", "tags": ["..."]}}], "optional": [{{"poi_id": "xxx", "reason": "...", "tags": ["..."]}}]}}
"""

    try:
        llm = get_llm()
        if is_structured_output_supported():
            from pydantic import BaseModel, Field

            class _PickItem(BaseModel):
                poi_id: str
                reason: Optional[str] = None
                tags: List[str] = Field(default_factory=list)

            class _PickOut(BaseModel):
                summary: Optional[str] = None
                must: List[_PickItem] = Field(default_factory=list)
                optional: List[_PickItem] = Field(default_factory=list)

            resp = await llm.with_structured_output(
                _PickOut, method="function_calling"
            ).ainvoke(prompt)
            must_ids = [m.poi_id for m in resp.must]
            optional_ids = [o.poi_id for o in resp.optional]
            summary = resp.summary
            raw_must = [m.model_dump() for m in resp.must]
            raw_optional = [o.model_dump() for o in resp.optional]
        else:
            raw = await llm.ainvoke(prompt)
            text = raw.content if hasattr(raw, "content") else str(raw)
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                raise ValueError("LLM 响应不含 JSON")
            data = json.loads(m.group(0))
            must_ids = [item["poi_id"] for item in data.get("must", []) if item.get("poi_id")]
            optional_ids = [item["poi_id"] for item in data.get("optional", []) if item.get("poi_id")]
            summary = data.get("summary")
            raw_must = data.get("must", [])
            raw_optional = data.get("optional", [])

        # 验证：去除两边重复（must 优先）+ 去除不在池里的 id
        valid_ids = {p.get("poi_id") for p in pool if p.get("poi_id")}
        must_ids = [i for i in must_ids if i in valid_ids]
        optional_ids = [i for i in optional_ids if i in valid_ids and i not in must_ids]

        if not must_ids and not optional_ids:
            raise ValueError("LLM 返回空集")

        must_reasons, must_tags = _collect_explanations(raw_must, valid_ids)
        optional_reasons, optional_tags = _collect_explanations(raw_optional, valid_ids)
        reasons = {**must_reasons, **optional_reasons}
        tags = {**must_tags, **optional_tags}

        return {
            "must_ids": must_ids,
            "optional_ids": optional_ids,
            "reasons": reasons,
            "tags": tags,
            "summary": summary,
        }

    except Exception:
        logger.exception("pick_attractions_from_pool LLM call failed, falling back to rating")
        must_ids, optional_ids = _rating_based_fallback(pool, days)
        reasons = {poi_id: "按评分和行程天数自动推荐" for poi_id in must_ids}
        tags = {poi_id: ["高评分"] for poi_id in must_ids}
        return {
            "must_ids": must_ids,
            "optional_ids": optional_ids,
            "reasons": reasons,
            "tags": tags,
            "summary": "AI 推荐暂不可用，已按评分排序生成推荐",
        }
