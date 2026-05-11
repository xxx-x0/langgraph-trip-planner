import json
import re
from typing import Dict, Any, List, Optional

from ....models.schemas import TripPlan, TripRequest, DayPlan, Attraction, Meal


def _extract_json_array(text: str) -> Optional[List[Dict]]:
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    bracket_pattern = re.compile(r'\[[\s\S]*?\]', re.DOTALL)
    for match in bracket_pattern.finditer(text):
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            continue
    return None


def _build_poi_dict(poi: Dict) -> Dict:
    """从 AMap POI 数据构建完整字段字典，兼容 MCP 层不同序列化格式。"""
    result = {
        "id": poi.get("id", ""),
        "name": poi["name"],
        "address": poi.get("address", ""),
        "location": poi.get("location", ""),
        "type": poi.get("type", ""),
    }
    photos = poi.get("photos")
    if isinstance(photos, list) and photos:
        first = photos[0]
        result["photo"] = first.get("url", "") if isinstance(first, dict) else str(first)
    else:
        result["photo"] = poi.get("photo", "")

    biz_ext = poi.get("biz_ext")
    if isinstance(biz_ext, dict):
        result["rating"] = biz_ext.get("rating", "")
        result["cost"] = biz_ext.get("cost", "")
    else:
        result["rating"] = poi.get("rating", "")
        result["cost"] = poi.get("cost", "")

    return result


def _extract_poi_names(text: str) -> List[Dict]:
    pois = []
    try:
        data = None
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    data = parsed
                elif isinstance(parsed, dict):
                    data = [parsed]
            except json.JSONDecodeError:
                pass

            if data is None:
                try:
                    import ast
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, list):
                        data = parsed
                    elif isinstance(parsed, dict):
                        data = [parsed]
                except (ValueError, SyntaxError):
                    pass

            if data is None:
                for line in text.split('\n'):
                    line = line.strip()
                    if line.startswith("'text':") or line.startswith('"text":'):
                        content = line.split(':', 1)[1].strip().strip(',').strip('"').strip("'")
                        try:
                            parsed = json.loads(content)
                            if isinstance(parsed, dict) and "pois" in parsed:
                                data = [parsed]
                                break
                        except json.JSONDecodeError:
                            continue

        if data is None:
            json_start = text.find('{')
            if json_start >= 0:
                json_end = text.rfind('}') + 1
                try:
                    parsed = json.loads(text[json_start:json_end])
                    if isinstance(parsed, dict) and "pois" in parsed:
                        data = [parsed]
                except json.JSONDecodeError:
                    pass

        if data:
            for item in data:
                if isinstance(item, dict) and "text" in item:
                    try:
                        inner = json.loads(item["text"]) if isinstance(item["text"], str) else item["text"]
                        if isinstance(inner, dict) and "pois" in inner:
                            for poi in inner["pois"]:
                                if "name" in poi:
                                    pois.append(_build_poi_dict(poi))
                    except (json.JSONDecodeError, TypeError):
                        continue
                elif isinstance(item, dict) and "pois" in item:
                    for poi in item["pois"]:
                        if "name" in poi:
                            pois.append(_build_poi_dict(poi))
    except Exception:
        pass

    return pois


def _repair_json(json_str: str) -> str:
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    json_str = re.sub(r"'", '"', json_str)
    json_str = re.sub(r'\bNaN\b', 'null', json_str)
    json_str = re.sub(r'\bInfinity\b', 'null', json_str)
    json_str = re.sub(r'\b-infinity\b', 'null', json_str, flags=re.IGNORECASE)
    json_str = re.sub(r'(\{|,)\s*([a-zA-Z_]\w*)\s*:', r'\1"\2":', json_str)
    return json_str


def _validate_plan_coordinates(trip_plan: TripPlan) -> TripPlan:
    for day in trip_plan.days:
        for attr in day.attractions:
            if attr.location is not None:
                lon = attr.location.longitude
                lat = attr.location.latitude
                if not (73 < lon < 136 and 3 < lat < 54):
                    attr.location = None
        for meal in day.meals:
            if meal.location is not None:
                lon = meal.location.longitude
                lat = meal.location.latitude
                if not (73 < lon < 136 and 3 < lat < 54):
                    meal.location = None
    return trip_plan


def _parse_response(response_text: str, request: TripRequest) -> TripPlan:
    try:
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "{" in response_text and "}" in response_text:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            json_str = response_text[json_start:json_end]
        else:
            raise ValueError("响应中未找到JSON数据")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            print("⚠️ JSON解析失败，尝试修复...")
            repaired = _repair_json(json_str)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                print("⚠️ JSON修复后仍解析失败，尝试逐步截断...")
                data = None
                for end_offset in range(len(json_str) - 1, max(len(json_str) // 2, 100), -1):
                    if json_str[end_offset] == '}':
                        try:
                            candidate = json_str[:end_offset + 1] + "]}" if '"days"' in json_str[:end_offset] else json_str[:end_offset + 1]
                            data = json.loads(_repair_json(candidate))
                            break
                        except json.JSONDecodeError:
                            continue
                if data is None:
                    raise ValueError("JSON截断修复也失败")

        trip_plan = TripPlan(**data)
        return _validate_plan_coordinates(trip_plan)
    except Exception as e:
        if isinstance(data, dict):
            try:
                data.setdefault("overall_suggestions", "请根据行程安排提前确认景点开放时间和交通信息。")
                data.setdefault("budget", {
                    "total_attractions": 0,
                    "total_hotels": 0,
                    "total_meals": 0,
                    "total_transportation": 0,
                    "total": 0
                })
                data.setdefault("weather_info", [])
                if "days" in data and isinstance(data["days"], list):
                    for day in data["days"]:
                        if isinstance(day, dict):
                            day.setdefault("route_segments", [])
                            day.setdefault("meals", [])
                            if "attractions" in day and isinstance(day["attractions"], list):
                                for attr in day["attractions"]:
                                    if isinstance(attr, dict):
                                        attr.setdefault("visit_duration", 120)
                                        attr.setdefault("category", "景点")
                                        attr.setdefault("ticket_price", 0)
                trip_plan = TripPlan(**data)
                print("⚠️ JSON缺少部分字段，已自动补全")
                return _validate_plan_coordinates(trip_plan)
            except Exception as e2:
                raise ValueError(f"解析 JSON 失败（补全后仍失败）: {str(e2)}")
        raise ValueError(f"解析 JSON 失败: {str(e)}")


def _create_fallback_plan(request: TripRequest, state: Dict[str, Any] = None) -> TripPlan:
    from datetime import datetime, timedelta

    state = state or {}
    attractions_info = state.get("attractions_info", "")
    hotels_info = state.get("hotels_info", "")

    poi_names = _extract_poi_names(attractions_info) if attractions_info else []

    start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

    days = []
    for i in range(request.travel_days):
        current_date = start_date + timedelta(days=i)

        day_attractions = []
        if poi_names:
            day_pois = poi_names[i * 2:(i + 1) * 2]
            for j, poi in enumerate(day_pois):
                day_attractions.append(Attraction(
                    name=poi.get("name", f"{request.city}景点{j+1}"),
                    address=poi.get("address", f"{request.city}市"),
                    location=None,
                    visit_duration=120,
                    description="推荐景点（数据来源受限，建议自行确认详情）",
                    category="景点"
                ))
        if not day_attractions:
            day_attractions = [Attraction(
                name=f"{request.city}推荐景点",
                address=f"{request.city}市",
                location=None,
                visit_duration=120,
                description="请自行查询景点详情",
                category="景点"
            )]

        day_plan = DayPlan(
            date=current_date.strftime("%Y-%m-%d"),
            day_index=i,
            description=f"第{i+1}天行程",
            transportation=request.transportation,
            accommodation=request.accommodation,
            attractions=day_attractions,
            meals=[
                Meal(type="breakfast", name="当地特色早餐", description="当地特色早餐", cuisine="本地菜", source="nearby"),
                Meal(type="lunch", name="午餐推荐", description="午餐推荐", cuisine="本地菜", source="nearby"),
                Meal(type="dinner", name="晚餐推荐", description="晚餐推荐", cuisine="本地菜", source="popular")
            ]
        )
        days.append(day_plan)

    return TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=days,
        weather_info=[],
        overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程。由于部分数据获取受限，建议提前确认各景点的开放时间和详情。"
    )
