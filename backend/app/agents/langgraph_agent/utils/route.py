"""单日路线规划工具 — 直接调用 AMap 方向工具生成结构化 RouteSegment"""

import asyncio
import json
from typing import List, Dict, Any, Optional

from .geo import _haversine_distance
from ....services.langchain_amap_tools import (
    get_langchain_amap_service,
    _is_connection_error,
    _reset_mcp_client,
)


_TRANSPORT_TOOL_MAP = {
    "公共交通": "maps_direction_transit_integrated",
    "公交": "maps_direction_transit_integrated",
    "地铁": "maps_direction_transit_integrated",
    "驾车": "maps_direction_driving",
    "自驾": "maps_direction_driving",
    "骑行": "maps_direction_bicycling",
    "自行车": "maps_direction_bicycling",
    "单车": "maps_direction_bicycling",
    "步行": "maps_direction_walking",
}

_TOOL_MODE_LABEL = {
    "maps_direction_transit_integrated": "公交",
    "maps_direction_driving": "驾车",
    "maps_direction_bicycling": "骑行",
    "maps_direction_walking": "步行",
}


def _pick_tool_name(transportation: str) -> str:
    for key, tool in _TRANSPORT_TOOL_MAP.items():
        if key in transportation:
            return tool
    return "maps_direction_transit_integrated"


def _parse_distance(meters: Any) -> str:
    try:
        m = float(meters)
        if m < 1000:
            return f"{int(m)}米"
        return f"{m / 1000:.1f}公里"
    except (ValueError, TypeError):
        return str(meters)


def _parse_duration(seconds: Any) -> str:
    try:
        s = int(float(seconds))
        if s < 60:
            return "1分钟"
        return f"{s // 60}分钟"
    except (ValueError, TypeError):
        return str(seconds)


def _parse_amap_result(raw: Any, tool_name: str) -> Dict[str, str]:
    """从 AMap 方向工具返回值中提取 distance/duration/detail"""
    data = raw

    # 解包 MCP content_and_artifact 元组: (content_list, artifact)
    if isinstance(data, tuple) and len(data) >= 2:
        data = data[0]

    # 解包 content block 列表: [{"type": "text", "text": "{...}"}]
    if isinstance(data, list):
        for block in data:
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
                data = block["text"]
                break

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return {"distance": "", "duration": "", "detail": str(data)[:200]}

    if isinstance(data, dict) and "raw_result" in data:
        inner = data["raw_result"]
        if isinstance(inner, str):
            try:
                data = json.loads(inner)
            except (json.JSONDecodeError, TypeError):
                return {"distance": "", "duration": "", "detail": str(inner)[:200]}

    if not isinstance(data, dict):
        return {"distance": "", "duration": "", "detail": str(data)[:200]}

    if tool_name in ("maps_direction_walking", "maps_direction_driving", "maps_direction_bicycling"):
        paths = data.get("paths") or data.get("route", {}).get("paths", [])
        if paths and isinstance(paths, list):
            p = paths[0]
            distance = _parse_distance(p.get("distance", ""))
            duration = _parse_duration(p.get("duration", ""))
            steps = p.get("steps", [])
            detail_parts = []
            for step in steps[:5]:
                instruction = step.get("instruction", "") or step.get("action", "")
                if instruction:
                    detail_parts.append(instruction)
            detail = "；".join(detail_parts) if detail_parts else ""
            return {"distance": distance, "duration": duration, "detail": detail}

    if tool_name == "maps_direction_transit_integrated":
        transits = data.get("transits") or data.get("route", {}).get("transits", [])
        if transits and isinstance(transits, list):
            t = transits[0]
            duration = _parse_duration(t.get("duration", ""))
            distance = _parse_distance(t.get("distance", t.get("walking_distance", "")))
            segments = t.get("segments", [])
            detail_parts = []
            for seg in segments[:4]:
                bus = seg.get("bus", {})
                buslines = bus.get("buslines", [])
                if buslines:
                    line = buslines[0]
                    line_name = line.get("name", "")
                    departure = line.get("departure_stop", {}).get("name", "")
                    arrival = line.get("arrival_stop", {}).get("name", "")
                    if line_name:
                        part = f"乘坐{line_name}"
                        if departure:
                            part += f"({departure}"
                        if arrival:
                            part += f"→{arrival})"
                        elif departure:
                            part += ")"
                        detail_parts.append(part)
                walking = seg.get("walking", {})
                if walking and not buslines:
                    w_dist = walking.get("distance", "")
                    if w_dist:
                        detail_parts.append(f"步行{_parse_distance(w_dist)}")
            detail = "，".join(detail_parts) if detail_parts else ""
            return {"distance": distance, "duration": duration, "detail": detail}
        return {"distance": "", "duration": "", "detail": ""}

    return {"distance": "", "duration": "", "detail": str(data)[:200]}


def _fallback_segment(
    from_wp: Dict, to_wp: Dict, transportation: str
) -> Dict[str, str]:
    """AMap 调用失败时用 haversine 估算"""
    dist_km = _haversine_distance(
        from_wp["latitude"], from_wp["longitude"],
        to_wp["latitude"], to_wp["longitude"],
    )
    speed_map = {"步行": 5, "骑行": 15, "驾车": 40}
    speed = speed_map.get(transportation, 25)
    duration_min = max(int(dist_km / speed * 60), 1)
    return {
        "from_name": from_wp["name"],
        "to_name": to_wp["name"],
        "distance": f"{dist_km:.1f}公里" if dist_km >= 1 else f"{int(dist_km * 1000)}米",
        "duration": f"{duration_min}分钟",
        "mode": transportation if transportation in speed_map else "公交",
        "detail": f"约{dist_km:.1f}公里，预计{duration_min}分钟",
    }


def _candidate_tools(
    from_wp: Dict[str, Any],
    to_wp: Dict[str, Any],
    transportation: str,
) -> List[str]:
    """Pick useful AMap route tools for a segment, nearest modes first."""
    preferred = _pick_tool_name(transportation)
    dist_km = _haversine_distance(
        from_wp["latitude"], from_wp["longitude"],
        to_wp["latitude"], to_wp["longitude"],
    )
    if dist_km <= 1.5:
        ordered = [
            "maps_direction_walking",
            "maps_direction_bicycling",
            preferred,
            "maps_direction_driving",
            "maps_direction_transit_integrated",
        ]
    elif dist_km <= 5:
        ordered = [
            "maps_direction_bicycling",
            preferred,
            "maps_direction_driving",
            "maps_direction_transit_integrated",
            "maps_direction_walking",
        ]
    else:
        ordered = [
            preferred,
            "maps_direction_driving",
            "maps_direction_transit_integrated",
            "maps_direction_bicycling",
        ]

    deduped: List[str] = []
    for tool_name in ordered:
        if tool_name not in deduped:
            deduped.append(tool_name)
    return deduped


async def _invoke_route_tool(
    service: Any,
    tool_name: str,
    tool: Any,
    args: Dict[str, Any],
) -> tuple[Any, Any]:
    """Call a route tool with the existing reconnect behavior."""
    last_err: Optional[Exception] = None
    result = None
    for attempt in range(3):
        try:
            result = await asyncio.wait_for(tool.ainvoke(args), timeout=30.0)
            return tool, result
        except Exception as retry_e:
            last_err = retry_e
            if _is_connection_error(retry_e):
                print(f"⚠️ 路线工具连接异常 (尝试 {attempt+1}/3): {str(retry_e)[:100]}")
                await _reset_mcp_client()
                try:
                    tool = await service.get_tool(tool_name)
                except Exception:
                    tool = None
                if tool is None:
                    break
            elif attempt < 2:
                print(f"⚠️ 路线工具调用失败 (尝试 {attempt+1}/3): {str(retry_e)[:100]}")
                await asyncio.sleep(min(2 ** attempt, 5))
            else:
                break
    raise last_err or RuntimeError("路线工具调用失败")


async def compute_route_segments(
    waypoints: List[Dict],
    transportation: str,
    city: str,
) -> List[Dict]:
    """为有序路径点列表计算结构化路线段。

    Args:
        waypoints: [{"name": str, "longitude": float, "latitude": float}, ...]
                   顺序为 酒店→景点1→景点2→...→酒店
        transportation: 用户偏好的交通方式
        city: 城市名称
    Returns:
        RouteSegment 字典列表
    """
    if len(waypoints) < 2:
        return []

    service = get_langchain_amap_service()
    preferred_tool_name = _pick_tool_name(transportation)
    preferred_mode_label = _TOOL_MODE_LABEL.get(preferred_tool_name, "公交")
    tool_cache: Dict[str, Any] = {}

    segments = []
    for i in range(len(waypoints) - 1):
        from_wp = waypoints[i]
        to_wp = waypoints[i + 1]

        origin = f"{from_wp['longitude']},{from_wp['latitude']}"
        destination = f"{to_wp['longitude']},{to_wp['latitude']}"
        appended = False
        for tool_name in _candidate_tools(from_wp, to_wp, transportation):
            if tool_name not in tool_cache:
                try:
                    tool_cache[tool_name] = await service.get_tool(tool_name)
                except Exception as e:
                    print(f"⚠️ 路线工具 {tool_name} 加载失败: {e}")
                    tool_cache[tool_name] = None
            tool = tool_cache[tool_name]
            if tool is None:
                continue

            args: Dict[str, Any] = {"origin": origin, "destination": destination}
            if tool_name == "maps_direction_transit_integrated":
                args["city"] = city

            try:
                tool, result = await _invoke_route_tool(service, tool_name, tool, args)
                tool_cache[tool_name] = tool
                parsed = _parse_amap_result(result, tool_name)
                if not parsed["distance"] and not parsed["duration"]:
                    continue
                segments.append({
                    "from_name": from_wp["name"],
                    "to_name": to_wp["name"],
                    "distance": parsed["distance"],
                    "duration": parsed["duration"],
                    "mode": _TOOL_MODE_LABEL.get(tool_name, preferred_mode_label),
                    "detail": parsed["detail"],
                })
                appended = True
                break
            except Exception as e:
                print(f"⚠️ 路线段 {from_wp['name']}→{to_wp['name']} 的 {tool_name} 查询失败: {str(e)[:100]}")

        if not appended:
            segments.append(_fallback_segment(from_wp, to_wp, preferred_mode_label))

    return segments
