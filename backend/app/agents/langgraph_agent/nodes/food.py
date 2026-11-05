from typing import Dict, Any, List, Optional

import asyncio

from langchain_core.messages import SystemMessage, HumanMessage

from ..exceptions import _invoke_tool_with_retry, _invoke_llm_with_retry
from ..prompts import FOOD_AGENT_PROMPT
from ..state import TripPlannerState, DayPlanLocalState
from ....services.langchain_amap_tools import get_langchain_amap_service
from ....services.llm_service import get_llm
from ....models.schemas import DiningCategory

# maps_search_detail节点内限速；缓存归公共边界，失败计数仅限当前批次。
_detail_semaphore = asyncio.Semaphore(2)       # 最多 2 个并发 detail 请求
_detail_lock = asyncio.Lock()                   # 保护当前批次失败计数
_DETAIL_CIRCUIT_BREAKER_THRESHOLD = 3           # 连续失败 ≥3 暂停当前批次


CITY_FOOD_MAP = {
    "北京": {"cuisine": "京菜", "keywords": ["烤鸭", "涮羊肉", "炸酱面", "京菜"]},
    "上海": {"cuisine": "本帮菜", "keywords": ["本帮菜", "小笼包", "生煎", "上海菜"]},
    "成都": {"cuisine": "川菜", "keywords": ["火锅", "川菜", "串串", "担担面"]},
    "重庆": {"cuisine": "渝菜", "keywords": ["火锅", "小面", "渝菜", "酸辣粉"]},
    "广州": {"cuisine": "粤菜", "keywords": ["早茶", "粤菜", "煲仔饭", "肠粉"]},
    "深圳": {"cuisine": "粤菜", "keywords": ["粤菜", "潮汕菜", "海鲜", "早茶"]},
    "西安": {"cuisine": "陕菜", "keywords": ["肉夹馍", "羊肉泡馍", "凉皮", "陕菜"]},
    "杭州": {"cuisine": "杭帮菜", "keywords": ["杭帮菜", "西湖醋鱼", "龙井虾仁", "东坡肉"]},
    "南京": {"cuisine": "金陵菜", "keywords": ["盐水鸭", "鸭血粉丝", "金陵菜", "小笼包"]},
    "长沙": {"cuisine": "湘菜", "keywords": ["臭豆腐", "湘菜", "剁椒鱼头", "茶颜悦色"]},
    "武汉": {"cuisine": "鄂菜", "keywords": ["热干面", "豆皮", "鄂菜", "武昌鱼"]},
    "厦门": {"cuisine": "闽南菜", "keywords": ["沙茶面", "海蛎煎", "闽南菜", "海鲜"]},
    "昆明": {"cuisine": "滇菜", "keywords": ["过桥米线", "滇菜", "汽锅鸡", "鲜花饼"]},
    "大理": {"cuisine": "滇菜", "keywords": ["白族菜", "饵丝", "滇菜", "酸辣鱼"]},
    "丽江": {"cuisine": "滇菜", "keywords": ["纳西菜", "滇菜", "腊排骨", "鸡豆凉粉"]},
    "苏州": {"cuisine": "苏帮菜", "keywords": ["苏帮菜", "松鼠桂鱼", "阳春面", "苏式汤面"]},
    "天津": {"cuisine": "津菜", "keywords": ["狗不理", "煎饼果子", "津菜", "麻花"]},
    "青岛": {"cuisine": "鲁菜", "keywords": ["海鲜", "啤酒", "鲁菜", "烧烤"]},
    "哈尔滨": {"cuisine": "东北菜", "keywords": ["锅包肉", "东北菜", "红肠", "杀猪菜"]},
    "拉萨": {"cuisine": "藏餐", "keywords": ["酥油茶", "藏餐", "糌粑", "牦牛肉"]},
    "乌鲁木齐": {"cuisine": "新疆菜", "keywords": ["大盘鸡", "烤羊肉", "新疆菜", "手抓饭"]},
}


def _get_food_keywords(city: str, food_preference: str) -> list:
    city_info = CITY_FOOD_MAP.get(city, {"cuisine": "本地菜", "keywords": ["特色菜", "美食"]})
    if food_preference == "本地特色" or food_preference == "无特殊要求":
        return city_info["keywords"][:2]
    preference_keywords = {
        "川菜": ["川菜", "火锅", "麻辣"],
        "粤菜": ["粤菜", "早茶", "海鲜"],
        "日料": ["日料", "寿司", "拉面"],
        "西餐": ["西餐", "牛排", "意面"],
        "小吃": ["小吃", "特色小吃", "路边摊"],
        "火锅": ["火锅", "涮锅"],
        "烧烤": ["烧烤", "烤肉"],
        "海鲜": ["海鲜", "大排档"],
    }
    return preference_keywords.get(food_preference, [food_preference])


async def search_food_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🍜 执行节点: search_food_node")
    request = state["request"]
    attractions_info = state.get("attractions_info", "")

    service = get_langchain_amap_service()
    around_tool = await service.get_tool("maps_around_search")
    search_tool = await service.get_tool("maps_text_search")
    llm = get_llm()
    llm_with_tools = llm.bind_tools([around_tool, search_tool])

    food_keywords = _get_food_keywords(request.city, request.food_preference)
    city_info = CITY_FOOD_MAP.get(request.city, {"cuisine": "本地菜"})

    prompt = FOOD_AGENT_PROMPT + f"""
请搜索城市: {request.city} 的餐厅信息。

**用户美食偏好:** {request.food_preference}
**城市特色菜系:** {city_info.get("cuisine", "本地菜")}
**推荐搜索关键词:** {', '.join(food_keywords)}

**景点信息（用于周边搜索）:**
{attractions_info[:2000]}

请执行以下搜索:
1. 使用 maps_around_search 搜索景点周边的餐厅（从景点信息中提取坐标）
2. 使用 maps_text_search 搜索城市热门餐厅（关键词: {food_keywords[0]})
"""
    response = await _invoke_llm_with_retry(llm_with_tools, [SystemMessage(content=FOOD_AGENT_PROMPT), HumanMessage(content=prompt)])

    food_results = []
    for tool_call in response.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        tool = await service.get_tool(tool_name)
        if tool:
            tool_result = await _invoke_tool_with_retry(tool, tool_args)
            food_results.append(f"[{tool_name}]: {str(tool_result)}")

    if food_results:
        return {"food_info": "\n".join(food_results)}

    print("⚠️ search_food_node: LLM未调用工具，返回空数据")
    return {"food_info": ""}


def _find_coord_fuzzy(name: str, coords_list: List[Dict]) -> Optional[Dict]:
    for c in coords_list:
        if c["name"] == name:
            return c
    for c in coords_list:
        if name in c["name"] or c["name"] in name:
            return c
    suffixes = ["景区", "风景区", "风景名胜区", "公园", "博物馆", "博物院", "纪念馆", "遗址"]
    stripped = name
    for s in suffixes:
        stripped = stripped.replace(s, "")
    if stripped and stripped != name:
        for c in coords_list:
            c_stripped = c["name"]
            for s in suffixes:
                c_stripped = c_stripped.replace(s, "")
            if stripped in c_stripped or c_stripped in stripped:
                return c
    return None


BREAKFAST_KEYWORDS = ["早餐", "早茶", "包子", "粥店"]


def _parse_amap_poi_list(raw: Any) -> List[Dict[str, Any]]:
    """从高德工具返回中提取 POI 列表（含 id, location, biz_ext.rating 等）。"""
    import json as _json
    import ast
    data = raw
    for _ in range(3):
        if isinstance(data, str):
            try:
                data = _json.loads(data)
                continue
            except (_json.JSONDecodeError, TypeError):
                try:
                    data = ast.literal_eval(data)
                    continue
                except (ValueError, SyntaxError):
                    break
        if isinstance(data, list) and data and isinstance(data[0], dict) and "text" in data[0]:
            inner = data[0]["text"]
            if isinstance(inner, str):
                data = inner
                continue
        break

    pois = []
    if isinstance(data, dict):
        pois = [data] if data.get("name") else data.get("pois", [])
        if not pois and isinstance(data.get("data"), dict):
            pois = data["data"].get("pois", [])
        if not pois:
            for v in data.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    pois = v
                    break
    elif isinstance(data, list):
        pois = data

    result = []
    for p in pois or []:
        if not isinstance(p, dict):
            continue
        name = p.get("name") or ""
        if not name:
            continue
        item: Dict[str, Any] = {"name": str(name)}
        poi_id = p.get("id") or p.get("poi_id")
        if poi_id:
            item["poi_id"] = str(poi_id)
        addr = p.get("address")
        if addr:
            item["address"] = str(addr)
        loc_str = p.get("location")
        if isinstance(loc_str, str) and "," in loc_str:
            parts = loc_str.split(",")
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                if 73 < lon < 136 and 3 < lat < 54:
                    item["longitude"] = lon
                    item["latitude"] = lat
            except (ValueError, IndexError):
                pass
        biz = p.get("biz_ext") or p.get("business") or p
        if isinstance(biz, dict):
            rating = biz.get("rating") or biz.get("score")
            if rating:
                try:
                    item["rating"] = float(rating)
                except (TypeError, ValueError):
                    pass
            cost = biz.get("cost")
            if cost:
                try:
                    item["avg_cost"] = int(float(cost))
                except (TypeError, ValueError):
                    pass
            opentime = biz.get("opentime_today") or biz.get("opentime_week") or biz.get("open_time") or biz.get("opentime2")
            if opentime:
                item["open_hours"] = str(opentime)
            tel = biz.get("tel") or p.get("tel")
            if tel:
                item["tel"] = str(tel)
        item["type"] = str(p.get("type") or "")
        result.append(item)
    return result


async def _enrich_pois_with_detail(
    pois: List[Dict[str, Any]],
    detail_tool: Any,
    max_calls: int = 3,
    concurrency: int = 1,
) -> None:
    """对前 N 个无评分/营业时间的 POI 调 maps_search_detail 补全 business.rating/cost/opentime。

    调用入口统一限流和短期缓存；本批连续失败3次后停止，下一批允许恢复。
    """
    consecutive_failures = 0

    if not detail_tool or not pois:
        return

    candidates: List[Dict[str, Any]] = []
    for p in pois[:max_calls]:
        if not p.get("poi_id"):
            continue
        if not p.get("rating") or not p.get("open_hours") or not p.get("longitude"):
            candidates.append(p)

    if not candidates:
        return

    async def _one(poi: Dict[str, Any]) -> None:
        nonlocal consecutive_failures

        if consecutive_failures >= _DETAIL_CIRCUIT_BREAKER_THRESHOLD:
            return
        async with _detail_semaphore:
            # 调用前等 0.5s，拉低 QPS
            await asyncio.sleep(0.5)
            try:
                raw = await _invoke_tool_with_retry(
                    detail_tool, {"id": poi["poi_id"]},
                    max_retries=1, per_attempt_timeout=10.0,
                )
            except Exception as e:
                print(f" ⚠️ maps_search_detail[{poi.get('name')}] 失败: {str(e)[:80]}")
                async with _detail_lock:
                    consecutive_failures += 1
                    if consecutive_failures >= _DETAIL_CIRCUIT_BREAKER_THRESHOLD:
                        print(" 🔴 当前批次详情查询失败，暂停本批，下一批可重试")
                return

        enriched = _parse_amap_poi_list(raw)
        if not enriched:
            return
        detail = enriched[0]
        for key in ("rating", "avg_cost", "open_hours", "tel", "type"):
            if detail.get(key) and not poi.get(key):
                poi[key] = detail[key]
        if detail.get("longitude") and not poi.get("longitude"):
            poi["longitude"] = detail["longitude"]
            poi["latitude"] = detail["latitude"]

        # Candidate cache ownership is in the gateway; no permanent node cache/circuit.
        async with _detail_lock:
            consecutive_failures = 0

    # 串行执行以拉低 QPS（全局限流 + 0.5s 间隔 = 最高 ~2 QPS）
    for poi in candidates:
        await _one(poi)


def _rank_food_pois(
    pois: List[Dict[str, Any]],
    center_lon: Optional[float],
    center_lat: Optional[float],
    used_names: set[str],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """按 (有评分, rating desc, 距离 asc) 排序，去重 used_names，取 top_n。"""
    from ..utils.geo import _haversine_distance

    scored = []
    for p in pois:
        name = p.get("name", "").strip()
        if not name or name in used_names:
            continue
        rating = p.get("rating")
        dist_km = 99.0
        if center_lon is not None and p.get("longitude") and p.get("latitude"):
            dist_km = _haversine_distance(center_lat, center_lon, p["latitude"], p["longitude"])
            p["_dist_km"] = dist_km
        scored.append((
            0 if rating is not None else 1,
            -(rating or 0.0),
            dist_km,
            p,
        ))
    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    return [s[3] for s in scored[:top_n]]


def _poi_to_meal_record(p: Dict[str, Any], meal_type: str, source: str) -> Dict[str, Any]:
    """把候选 POI 转成 LLM 友好的 meal 记录（最终在 day_plan_generator 输出 Meal）。"""
    record: Dict[str, Any] = {
        "type": meal_type,
        "name": p.get("name", ""),
        "source": source,
    }
    if p.get("address"):
        record["address"] = p["address"]
    if p.get("longitude") and p.get("latitude"):
        record["location"] = {"longitude": p["longitude"], "latitude": p["latitude"]}
    if p.get("rating") is not None:
        record["rating"] = round(float(p["rating"]), 2)
    if p.get("avg_cost") is not None:
        record["avg_cost"] = int(p["avg_cost"])
    if p.get("open_hours"):
        record["open_hours"] = p["open_hours"]
    if p.get("tel"):
        record["tel"] = p["tel"]
    if p.get("_dist_km") is not None:
        record["distance"] = f"约 {p['_dist_km']:.1f} 公里"
    cuisine_tag = p.get("type") or ""
    if cuisine_tag:
        record["cuisine"] = cuisine_tag.split(";")[0].strip() or "本地菜"
    return record


async def day_food_search_node(state: DayPlanLocalState) -> Dict[str, Any]:
    """为当天搜索早午晚餐厅候选并按评分/距离排序，输出结构化 JSON 字符串。

    改造点：
    - 早餐围绕酒店坐标搜（早茶/早餐/包子/粥），8 点景点没开门时仍可用
    - 午餐围绕当日聚类中部景点搜，关键词按 day_index 轮换避免菜系雷同
    - 晚餐用城市级 maps_text_search 取热门餐厅
    - 对前 3 个 POI 串行调 maps_search_detail 拿 business.rating / cost / opentime（全局限流+熔断）
    """
    import json as _json
    from ..utils.geo import _extract_coordinates_regex

    day_index = state["day_index"]
    attraction_names = state["attraction_names"]
    city = state["city"]
    food_preference = state.get("food_preference", "本地特色")

    print(f"🍜 单日美食搜索: 第{day_index + 1}天, 景点: {attraction_names}")

    service = get_langchain_amap_service()
    around_tool = await service.get_tool("maps_around_search")
    text_tool = await service.get_tool("maps_text_search")
    detail_tool = await service.get_tool("maps_search_detail")

    food_keywords = _get_food_keywords(city, food_preference)
    city_info = CITY_FOOD_MAP.get(city, {"cuisine": "本地菜", "keywords": ["特色菜"]})

    attractions_info = state.get("attractions_info", "")
    all_coords = _extract_coordinates_regex(attractions_info)
    day_hotel_loc = state.get("day_hotel_location")
    hotel_lon = hotel_lat = None
    if isinstance(day_hotel_loc, dict):
        hotel_lon = day_hotel_loc.get("longitude")
        hotel_lat = day_hotel_loc.get("latitude")

    day_cluster = state.get("day_cluster") or []
    cluster_coords: List[Dict[str, Any]] = []
    for c in day_cluster:
        if c.get("longitude") and c.get("latitude"):
            cluster_coords.append({"name": c["name"], "longitude": c["longitude"], "latitude": c["latitude"]})

    # 早餐中心：优先酒店，回退到首景点
    breakfast_center = None
    if hotel_lon and hotel_lat:
        breakfast_center = (hotel_lon, hotel_lat)
    elif cluster_coords:
        breakfast_center = (cluster_coords[0]["longitude"], cluster_coords[0]["latitude"])
    elif attraction_names:
        coord = _find_coord_fuzzy(attraction_names[0], all_coords)
        if coord:
            breakfast_center = (coord["longitude"], coord["latitude"])

    # 午餐中心：聚类中部景点
    lunch_center = None
    if cluster_coords:
        mid = len(cluster_coords) // 2
        lunch_center = (cluster_coords[mid]["longitude"], cluster_coords[mid]["latitude"])
    elif attraction_names:
        idx = min(len(attraction_names) // 2, len(attraction_names) - 1)
        coord = _find_coord_fuzzy(attraction_names[idx], all_coords)
        if coord:
            lunch_center = (coord["longitude"], coord["latitude"])

    # 按日轮换的午餐菜系关键词
    cuisine_keywords = city_info.get("keywords") or food_keywords or ["美食"]
    lunch_keyword = cuisine_keywords[day_index % len(cuisine_keywords)]

    async def _around(center: tuple[float, float] | None, keyword: str, radius: str) -> List[Dict[str, Any]]:
        if not center or not around_tool:
            return []
        location_str = f"{center[0]},{center[1]}"
        try:
            raw = await _invoke_tool_with_retry(around_tool, {
                "keywords": keyword,
                "location": location_str,
                "radius": radius,
            }, max_retries=1, per_attempt_timeout=15.0)
        except Exception as e:
            print(f" ⚠️ around_search [{keyword} @ {location_str}] 失败: {str(e)[:80]}")
            return []
        return _parse_amap_poi_list(raw)

    breakfast_pois: List[Dict[str, Any]] = []
    for kw in BREAKFAST_KEYWORDS[:2]:
        breakfast_pois.extend(await _around(breakfast_center, kw, "1500"))

    lunch_pois = await _around(lunch_center, lunch_keyword, "2000")

    dinner_pois: List[Dict[str, Any]] = []
    if text_tool:
        try:
            dinner_kw = f"{city}{city_info.get('cuisine', '美食')}"
            raw = await _invoke_tool_with_retry(text_tool, {
                "keywords": dinner_kw,
                "city": city,
            }, max_retries=1, per_attempt_timeout=15.0)
            dinner_pois = _parse_amap_poi_list(raw)
        except Exception as e:
            print(f" ⚠️ text_search 失败: {str(e)[:80]}")

    # 详情增强：串行执行（全局限流 + 熔断器），max_calls=3 每批
    await _enrich_pois_with_detail(breakfast_pois, detail_tool, max_calls=3)
    await _enrich_pois_with_detail(lunch_pois, detail_tool, max_calls=3)
    await _enrich_pois_with_detail(dinner_pois, detail_tool, max_calls=3)

    used_names: set[str] = set()
    breakfast_top = _rank_food_pois(
        breakfast_pois,
        breakfast_center[0] if breakfast_center else None,
        breakfast_center[1] if breakfast_center else None,
        used_names, top_n=3,
    )
    used_names.update(p["name"] for p in breakfast_top)

    lunch_top = _rank_food_pois(
        lunch_pois,
        lunch_center[0] if lunch_center else None,
        lunch_center[1] if lunch_center else None,
        used_names, top_n=3,
    )
    used_names.update(p["name"] for p in lunch_top)

    dinner_top = _rank_food_pois(dinner_pois, None, None, used_names, top_n=3)

    payload = {
        "breakfast": [_poi_to_meal_record(p, "breakfast", "nearby") for p in breakfast_top],
        "lunch": [_poi_to_meal_record(p, "lunch", "nearby") for p in lunch_top],
        "dinner": [_poi_to_meal_record(p, "dinner", "popular") for p in dinner_top],
        "lunch_keyword": lunch_keyword,
        "day_index": day_index,
    }
    day_food_info = _json.dumps(payload, ensure_ascii=False)
    total = len(breakfast_top) + len(lunch_top) + len(dinner_top)
    rated = sum(1 for arr in (breakfast_top, lunch_top, dinner_top) for p in arr if p.get("rating") is not None)
    print(f" ✅ 第{day_index + 1}天美食候选: {total}家 (评分增强 {rated}家), 午餐关键词='{lunch_keyword}'")
    return {"day_food_info": day_food_info}


# ============ 多类别餐饮候选池（骨架阶段） ============

_DINING_KEYWORDS = {
    DiningCategory.MAIN: ("餐厅 美食", 6),
    DiningCategory.SNACK: ("小吃 街边小吃", 4),
    DiningCategory.DESSERT: ("甜品 蛋糕 茶饮", 4),
    DiningCategory.CAFE: ("咖啡馆", 4),
    DiningCategory.LATE_NIGHT: ("夜宵 烧烤 大排档", 4),
}


def _day_center(day_cluster: List[Dict[str, Any]]) -> Optional[tuple[float, float]]:
    """计算当日景点经纬度算术平均；无有效坐标返回 None"""
    coords = [
        (c["longitude"], c["latitude"])
        for c in (day_cluster or [])
        if isinstance(c.get("longitude"), (int, float))
        and isinstance(c.get("latitude"), (int, float))
        and 73 < c["longitude"] < 136 and 3 < c["latitude"] < 54
    ]
    if not coords:
        return None
    return (
        sum(x for x, _ in coords) / len(coords),
        sum(y for _, y in coords) / len(coords),
    )


async def _search_dining_category(
    category: DiningCategory,
    center: Optional[tuple[float, float]],
    city: str,
    food_preference: str = "",
) -> List[Dict[str, Any]]:
    """跑一次 amap POI 搜索；center 为 None 时走城市文本搜索"""
    keyword, _top_n = _DINING_KEYWORDS[category]
    if category == DiningCategory.MAIN and food_preference:
        keyword = CITY_FOOD_MAP.get(city, {}).get("cuisine", "餐厅") if food_preference == "本地特色" else ("餐厅" if food_preference == "无特殊要求" else food_preference)
    service = get_langchain_amap_service()

    if center is not None:
        tool = await service.get_tool("maps_around_search")
        if tool is None:
            return []
        try:
            raw = await _invoke_tool_with_retry(
                tool,
                {"keywords": keyword, "location": f"{center[0]},{center[1]}", "radius": "1500"},
                max_retries=2, per_attempt_timeout=15.0,
            )
        except Exception as e:
            print(f" ⚠️ dining[{category.value}] around 失败: {str(e)[:80]}")
            return []
    else:
        tool = await service.get_tool("maps_text_search")
        if tool is None:
            return []
        try:
            raw = await _invoke_tool_with_retry(
                tool, {"keywords": keyword, "city": city},
                max_retries=2, per_attempt_timeout=15.0,
            )
        except Exception as e:
            print(f" ⚠️ dining[{category.value}] text 失败: {str(e)[:80]}")
            return []

    return _parse_amap_poi_list(raw)


def _poi_to_dining_candidate(
    p: Dict[str, Any], category: DiningCategory, source: str
) -> Dict[str, Any]:
    """把 _parse_amap_poi_list 的 POI dict 转成 DiningCandidate dict"""
    cand: Dict[str, Any] = {
        "name": p.get("name", ""),
        "category": category.value,
        "source": source,
    }
    if p.get("address"):
        cand["address"] = p["address"]
    if p.get("longitude") and p.get("latitude"):
        cand["location"] = {"longitude": p["longitude"], "latitude": p["latitude"]}
    if p.get("rating") is not None:
        cand["rating"] = round(float(p["rating"]), 2)
    if p.get("avg_cost") is not None:
        cand["avg_cost"] = int(p["avg_cost"])
    if p.get("open_hours"):
        cand["open_hours"] = p["open_hours"]
    if p.get("tel"):
        cand["tel"] = p["tel"]
    if p.get("poi_id"):
        cand["poi_id"] = p["poi_id"]
    cuisine_tag = (p.get("type") or "").split(";")[-1].strip()
    if cuisine_tag:
        cand["cuisine"] = cuisine_tag
    from datetime import datetime, timezone
    cand['recommendation'] = {'source':'高德地图 POI', 'queried_at':datetime.now(timezone.utc).isoformat()}
    return cand


async def search_dining_pool_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """骨架阶段：逐类搜索避免同一高德接口的并发限流，并补齐候选坐标。"""
    print("🍴 执行节点: search_dining_pool_node")
    request = state["request"]
    clusters_data: List[List[Dict[str, Any]]] = state.get("clusters_data", []) or []
    travel_days = request.travel_days

    while len(clusters_data) < travel_days:
        clusters_data.append([])

    pools: List[Dict[str, Any]] = []
    for day_idx in range(travel_days):
        day_cluster = clusters_data[day_idx] if day_idx < len(clusters_data) else []
        from ....services.recommendations import cluster_attractions
        pool = await search_dining_for_day(request, cluster_attractions(day_cluster))
        pools.append(pool)
        total = sum(len(v) for v in pool.values())
        print(f" ✅ 第{day_idx + 1}天餐饮候选池: 共 {total} 家")

    return {"dining_pool": pools}


async def search_dining_for_day(request, attractions, start_time=None, schedule=None, hotel=None, meals=None,
                                *, anchors_override=None, main_only=False, detail_limit=None):
    from ....services.recommendations import cluster_attractions, meal_anchors, intent_for, explain_dining, dining_for_slot
    from ....models.schemas import DiningCandidate
    anchors = anchors_override or meal_anchors(attractions, start_time or request.default_day_start_time, schedule, hotel, meals)
    centers = []
    for before, after, _ in anchors.values():
        # Recovery searches both sides of the actual meal gap, including the departure hotel.
        places = (before, after) if anchors_override else (before or after,)
        for place in places:
            loc = place.location if place else None
            center = (loc.longitude, loc.latitude) if loc else None
            if center not in centers: centers.append(center)
    if any(centers): centers = [c for c in centers if c is not None]
    categories = (DiningCategory.MAIN,) if main_only else tuple(DiningCategory)
    results = []
    for cat in categories:
        found = []
        for center in ((centers + [None] if request.dining_style == "dedicated" and None not in centers else centers) if cat == DiningCategory.MAIN else centers[:1]):
            try:
                found.extend(await _search_dining_category(cat, center, request.city, food_preference=request.food_preference))
            except Exception as error:
                print(f"餐饮查询未成功: {type(error).__name__}")
        if cat == DiningCategory.MAIN and request.meal_budget_per_person and not any(
                p.get('avg_cost') is not None and p['avg_cost'] <= request.meal_budget_per_person for p in found):
            # Cuisine-specific restaurants may all exceed the requested cap. Offer ordinary meals too.
            supplement = []
            for center in centers:
                try:
                    supplement.extend(await _search_dining_category(cat, center, request.city, food_preference='快餐'))
                except Exception as error:
                    print(f'餐饮预算补充查询未成功: {type(error).__name__}')
            # Around-search may omit ALL coordinates/prices. Reserve detail calls for both queries
            # instead of spending the whole bounded batch on the first cuisine's expensive venues.
            from itertools import zip_longest
            found = [p for pair in zip_longest(found,supplement) for p in pair if p is not None]
        results.append(found)
    pool = {}
    for cat, res in zip(categories, results):
        # Preserve spatial variety before ratings; deduplicate actual POI IDs.
        unique = {p.get('poi_id') or p['name']:p for p in res}
        candidates = [DiningCandidate.model_validate(_poi_to_dining_candidate(p,cat,'nearby' if any(centers) else 'city_search')) for p in unique.values()]
        explain_dining(candidates, attractions, intent_for(request), start_time or request.default_day_start_time, schedule, hotel, meals, anchors_override=anchors_override)
        selected = []
        for slot in tuple(anchors) if cat == DiningCategory.MAIN else ('lunch',):
            for candidate in dining_for_slot(candidates,slot,intent_for(request))[:(5 if cat == DiningCategory.MAIN else 3)]:
                if candidate not in selected: selected.append(candidate)
        selected = selected[:8]
        raw_selected = [unique[c.poi_id or c.name] for c in selected]
        if any(p.get('poi_id') and (not p.get('open_hours') or not p.get('longitude')) for p in raw_selected):
            detail_tool = await get_langchain_amap_service().get_tool('maps_search_detail')
            await _enrich_pois_with_detail(raw_selected,detail_tool,max_calls=detail_limit if detail_limit is not None else len(raw_selected))
        selected = [DiningCandidate.model_validate(_poi_to_dining_candidate(p,cat,'nearby' if any(centers) else 'city_search')) for p in raw_selected]
        # A closure supplied by the provider is retained as a reason, never advertised as open.
        explain_dining(selected,attractions,intent_for(request),start_time or request.default_day_start_time,schedule,hotel,meals,anchors_override=anchors_override)
        pool[cat.value] = [c.model_dump(mode='json') for c in selected]
    return pool
