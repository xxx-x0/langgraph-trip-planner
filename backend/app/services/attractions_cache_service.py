"""Persistent AMap attraction cache service."""

import ast
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert

from ..database import async_session
from ..models.db_models import AttractionCache
from .langchain_amap_tools import get_langchain_amap_service


@dataclass
class CachedAttraction:
    """Standardized POI returned to LangGraph nodes."""

    name: str
    address: Optional[str] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    category: Optional[str] = None
    rating: Optional[float] = None
    ticket_price: Optional[str] = None
    image_url: Optional[str] = None
    poi_id: Optional[str] = None
    amap_type: Optional[str] = None
    description: Optional[str] = None


AMAP_SEARCH_KEYWORDS = ["景点", "公园", "博物馆", "古迹", "广场", "寺庙", "购物中心", "美食街"]

AMAP_CATEGORY_RULES = [
    (("宗教", "寺庙", "教堂", "清真寺", "道观", "寺", "庙"), "宗教"),
    (("动物园", "植物园", "水族馆", "海洋馆", "亲子", "儿童乐园", "主题公园"), "亲子"),
    (("博物馆", "纪念馆", "展览馆", "美术馆", "文化宫", "文物古迹", "故居", "陵", "古迹", "科教文化"), "历史文化"),
    (("购物中心", "商业街", "购物", "商场"), "购物"),
    (("美食街", "餐饮", "美食", "夜市", "小吃", "中餐厅"), "美食街区"),
    (("游乐", "娱乐", "剧场", "影院", "休闲", "运动", "体育", "温泉"), "休闲娱乐"),
    (("商务住宅", "地标", "观光", "会展中心", "城市广场"), "现代都市"),
    (("公园", "湖", "山", "海滨", "森林", "湿地", "自然", "风景名胜", "公园广场"), "自然风光"),
]

TYPECODE_CATEGORY_RULES = [
    ("110205", "宗教"),
    ("110204", "历史文化"),
    ("110207", "历史文化"),
    ("110208", "历史文化"),
    ("1101", "自然风光"),
    ("1102", "自然风光"),
    ("1103", "现代都市"),
    ("1104", "自然风光"),
    ("14", "历史文化"),
    ("06", "购物"),
    ("05", "美食街区"),
    ("08", "休闲娱乐"),
    ("11", "自然风光"),
]

ATTRACTION_SUFFIX_RE = re.compile(r"(风景名胜区|风景区|景区|旅游区|度假区|步行街|商业街)$")


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", [], {}):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_location(location: Any) -> Optional[tuple[float, float]]:
    if isinstance(location, str) and "," in location:
        lng, lat = location.split(",", 1)
        longitude = _safe_float(lng.strip())
        latitude = _safe_float(lat.strip())
    elif isinstance(location, dict):
        longitude = _safe_float(location.get("longitude") or location.get("lng"))
        latitude = _safe_float(location.get("latitude") or location.get("lat"))
    elif isinstance(location, (list, tuple)) and len(location) >= 2:
        longitude = _safe_float(location[0])
        latitude = _safe_float(location[1])
    else:
        return None

    if longitude is None or latitude is None:
        return None
    return longitude, latitude


def _is_valid_coordinate(longitude: Optional[float], latitude: Optional[float]) -> bool:
    return longitude is not None and latitude is not None and 73 < longitude < 136 and 3 < latitude < 54


def _category_from_typecode(typecode: Optional[str]) -> Optional[str]:
    if not typecode:
        return None
    codes = [c.strip() for c in str(typecode).split("|") if c.strip()]
    for code in codes:
        for prefix, category in TYPECODE_CATEGORY_RULES:
            if code.startswith(prefix):
                return category
    return None


def _normalize_category(amap_type: Optional[str], typecode: Optional[str] = None) -> str:
    if amap_type:
        for keywords, category in AMAP_CATEGORY_RULES:
            if any(keyword in amap_type for keyword in keywords):
                return category
    tc_category = _category_from_typecode(typecode)
    if tc_category:
        return tc_category
    return "其他"


def _extract_photo(poi: dict[str, Any]) -> Optional[str]:
    photos = poi.get("photos")
    if isinstance(photos, list) and photos:
        first = photos[0]
        if isinstance(first, dict):
            return first.get("url") or first.get("image_url")
        return str(first)
    return poi.get("photo") or poi.get("image_url")


def _extract_biz_ext_value(poi: dict[str, Any], key: str) -> Any:
    biz_ext = poi.get("biz_ext")
    if isinstance(biz_ext, dict):
        return biz_ext.get(key)
    return poi.get(key)


def _normalize_poi(city: str, poi: dict[str, Any]) -> Optional[dict[str, Any]]:
    name = str(poi.get("name") or "").strip()
    if not name:
        return None

    location = _extract_location(poi.get("location"))
    if location is None and ("longitude" in poi or "latitude" in poi):
        location = _extract_location({"longitude": poi.get("longitude"), "latitude": poi.get("latitude")})
    longitude = location[0] if location else None
    latitude = location[1] if location else None
    if location and not _is_valid_coordinate(longitude, latitude):
        return None

    amap_type = poi.get("type") or poi.get("amap_type")
    typecode = poi.get("typecode")
    rating = _safe_float(_extract_biz_ext_value(poi, "rating"))
    ticket_price = _extract_biz_ext_value(poi, "cost") or poi.get("ticket_price")
    if ticket_price not in (None, ""):
        ticket_price = str(ticket_price)
    else:
        ticket_price = None

    return {
        "city": city.strip(),
        "name": name,
        "poi_id": poi.get("id") or poi.get("poi_id"),
        "address": poi.get("address") or None,
        "longitude": longitude,
        "latitude": latitude,
        "amap_type": amap_type or typecode,
        "category": _normalize_category(amap_type, typecode),
        "rating": rating,
        "ticket_price": ticket_price,
        "image_url": _extract_photo(poi),
        "last_updated": datetime.utcnow(),
    }


def _coerce_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return value


def _extract_pois_from_result(result: Any) -> list[dict[str, Any]]:
    parsed = _coerce_jsonish(result)

    if isinstance(parsed, dict) and "raw_result" in parsed:
        return _extract_pois_from_result(parsed["raw_result"])

    if isinstance(parsed, dict) and "text" in parsed:
        return _extract_pois_from_result(parsed["text"])

    if isinstance(parsed, dict) and isinstance(parsed.get("pois"), list):
        return [poi for poi in parsed["pois"] if isinstance(poi, dict)]

    if isinstance(parsed, list):
        pois: list[dict[str, Any]] = []
        for item in parsed:
            if isinstance(item, dict) and "name" in item:
                pois.append(item)
            elif isinstance(item, dict) and ("text" in item or "pois" in item or "raw_result" in item):
                pois.extend(_extract_pois_from_result(item))
        return pois

    if isinstance(parsed, str):
        start = parsed.find("{")
        end = parsed.rfind("}")
        if start >= 0 and end > start:
            return _extract_pois_from_result(parsed[start:end + 1])

    return []


def _extract_detail_from_result(result: Any) -> Optional[dict[str, Any]]:
    parsed = _coerce_jsonish(result)
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                if "text" in item:
                    inner = _coerce_jsonish(item["text"])
                    if isinstance(inner, dict) and inner.get("id"):
                        return inner
                elif item.get("id") and item.get("name"):
                    return item
        return None
    if isinstance(parsed, dict):
        if parsed.get("id") and parsed.get("name"):
            return parsed
        if "raw_result" in parsed:
            return _extract_detail_from_result(parsed["raw_result"])
        if "text" in parsed:
            return _extract_detail_from_result(parsed["text"])
    return None


def _row_to_cached(row: AttractionCache) -> CachedAttraction:
    return CachedAttraction(
        name=row.name,
        address=row.address,
        longitude=row.longitude,
        latitude=row.latitude,
        category=row.category,
        rating=row.rating,
        ticket_price=row.ticket_price,
        image_url=row.image_url,
        poi_id=row.poi_id,
        amap_type=row.amap_type,
        description=row.description,
    )


def _dict_to_cached(data: dict[str, Any]) -> CachedAttraction:
    return CachedAttraction(
        name=data["name"],
        address=data.get("address"),
        longitude=data.get("longitude"),
        latitude=data.get("latitude"),
        category=data.get("category"),
        rating=data.get("rating"),
        ticket_price=data.get("ticket_price"),
        image_url=data.get("image_url"),
        poi_id=data.get("poi_id"),
        amap_type=data.get("amap_type"),
        description=data.get("description"),
    )


async def _invoke_tool_with_retry_local(
    tool: Any,
    args: dict[str, Any],
    max_retries: int = 2,
    per_attempt_timeout: float = 15.0,
) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.wait_for(tool.ainvoke(args), timeout=per_attempt_timeout)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("工具调用失败")


class AttractionsCacheService:
    def __init__(self, session_factory=async_session):
        self.session_factory = session_factory

    async def get_attractions(
        self,
        city: str,
        min_count: int = 20,
        categories: Optional[list[str]] = None,
    ) -> list[CachedAttraction]:
        city = city.strip()
        cached = await self._safe_query_db(city, categories)
        if len(cached) >= min_count:
            return cached

        all_cached = await self._safe_query_db(city, None)
        if categories and len(cached) < min_count and len(all_cached) >= min_count:
            print(f"⚠️ 景点缓存按分类过滤不足({len(cached)} < {min_count})，返回城市全量缓存")
            return all_cached

        fetched: list[dict[str, Any]] = []
        try:
            fetched = await self._fetch_from_amap(city)
            try:
                await self._persist(city, fetched)
            except Exception as e:
                print(f"⚠️ 景点缓存写入失败，使用本次高德结果继续: {e}")
                normalized = [p for p in (_normalize_poi(city, poi) for poi in fetched) if p]
                return [_dict_to_cached(p) for p in normalized]
        except Exception as e:
            print(f"⚠️ 景点高德拉取失败: {e}")
            if all_cached:
                return all_cached
            raise

        refreshed = await self._safe_query_db(city, categories)
        if categories and len(refreshed) < min_count:
            return await self._safe_query_db(city, None)
        return refreshed

    async def find_by_name(self, city: str, name: str) -> Optional[CachedAttraction]:
        city = city.strip()
        name = name.strip()
        if not name:
            return None

        async with self.session_factory() as session:
            exact = await session.scalar(
                select(AttractionCache).where(
                    AttractionCache.city == city,
                    AttractionCache.name == name,
                )
            )
            if exact:
                return _row_to_cached(exact)

            base_name = ATTRACTION_SUFFIX_RE.sub("", name)
            if base_name and base_name != name:
                fuzzy = await session.scalar(
                    select(AttractionCache)
                    .where(AttractionCache.city == city, AttractionCache.name.like(f"%{base_name}%"))
                    .order_by(AttractionCache.id)
                )
                if fuzzy:
                    return _row_to_cached(fuzzy)

        result = await self._fetch_keyword(city, name)
        normalized = [p for p in (_normalize_poi(city, poi) for poi in result) if p]
        if not normalized:
            return None

        await self._persist(city, [normalized[0]])
        return _dict_to_cached(normalized[0])

    async def refresh_city(self, city: str) -> int:
        city = city.strip()
        pois = await self._fetch_from_amap(city)
        await self.clear_city(city)
        return await self._persist(city, pois)

    async def clear_city(self, city: str) -> int:
        city = city.strip()
        async with self.session_factory() as session:
            result = await session.execute(delete(AttractionCache).where(AttractionCache.city == city))
            await session.commit()
            return int(result.rowcount or 0)

    async def get_stats(self) -> dict[str, int]:
        async with self.session_factory() as session:
            attractions = await session.scalar(select(func.count(AttractionCache.id)))
            cities = await session.scalar(select(func.count(func.distinct(AttractionCache.city))))
            return {"cities": int(cities or 0), "attractions": int(attractions or 0)}

    async def _safe_query_db(self, city: str, categories: Optional[list[str]]) -> list[CachedAttraction]:
        try:
            return await self._query_db(city, categories)
        except Exception as e:
            print(f"⚠️ 景点缓存读取失败，视为未命中: {e}")
            return []

    async def _query_db(self, city: str, categories: Optional[list[str]]) -> list[CachedAttraction]:
        async with self.session_factory() as session:
            stmt = select(AttractionCache).where(AttractionCache.city == city)
            if categories:
                stmt = stmt.where(AttractionCache.category.in_(categories))
            stmt = stmt.order_by(AttractionCache.id)
            rows = (await session.scalars(stmt)).all()
            return [_row_to_cached(row) for row in rows]

    async def _fetch_from_amap(self, city: str, target_count: int = 80) -> list[dict[str, Any]]:
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        failures = 0

        for keyword in AMAP_SEARCH_KEYWORDS:
            if len(results) >= target_count:
                break
            try:
                pois = await self._fetch_keyword(city, keyword)
            except Exception as e:
                failures += 1
                print(f"⚠️ 高德景点关键词搜索失败({city}/{keyword}): {e}")
                if failures >= 5 and not results:
                    raise
                continue

            for poi in pois:
                name = str(poi.get("name") or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                results.append(poi)
                if len(results) >= target_count:
                    break

        if not results and failures:
            raise RuntimeError(f"高德景点搜索失败: {city}")

        if results:
            try:
                await self._enrich_with_details(results)
            except Exception as e:
                print(f"⚠️ 景点详情批量补全异常，使用搜索原始数据继续: {e}")

        return results

    async def _fetch_keyword(self, city: str, keyword: str) -> list[dict[str, Any]]:
        service = get_langchain_amap_service()
        search_tool = await service.get_tool("maps_text_search")
        if search_tool is None:
            raise RuntimeError("maps_text_search 工具不可用")

        result = await _invoke_tool_with_retry_local(
            search_tool,
            {"keywords": keyword, "city": city, "citylimit": "true"},
        )
        return _extract_pois_from_result(result)

    async def _fetch_detail(self, poi_id: str) -> Optional[dict[str, Any]]:
        service = get_langchain_amap_service()
        tool = await service.get_tool("maps_search_detail")
        if tool is None:
            return None
        for attempt in range(3):
            try:
                result = await _invoke_tool_with_retry_local(
                    tool,
                    {"id": poi_id},
                    max_retries=0,
                    per_attempt_timeout=10.0,
                )
                return _extract_detail_from_result(result)
            except Exception as e:
                msg = str(e)
                is_qps = "CUQPS" in msg or "EXCEEDED" in msg
                if attempt < 2 and is_qps:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if attempt == 2 or not is_qps:
                    print(f"⚠️ maps_search_detail 失败 (id={poi_id}): {msg[:120]}")
                return None
        return None

    async def _enrich_with_details(
        self,
        pois: list[dict[str, Any]],
        concurrency: int = 3,
    ) -> None:
        """In-place 用 maps_search_detail 补全 location/中文 type/rating/cost 等字段。"""
        targets = [p for p in pois if p.get("id") or p.get("poi_id")]
        if not targets:
            return

        sem = asyncio.Semaphore(concurrency)

        async def enrich_one(poi: dict[str, Any]) -> None:
            poi_id = poi.get("id") or poi.get("poi_id")
            async with sem:
                detail = await self._fetch_detail(poi_id)
            if not detail:
                return
            if detail.get("location") and not poi.get("location"):
                poi["location"] = detail["location"]
            if detail.get("type"):
                poi["type"] = detail["type"]
            if detail.get("rating") and not poi.get("rating"):
                poi["rating"] = detail["rating"]
            if detail.get("cost") and not poi.get("cost"):
                poi["cost"] = detail["cost"]
            if detail.get("address") and not poi.get("address"):
                poi["address"] = detail["address"]
            if detail.get("photo") and not poi.get("photo"):
                poi["photo"] = detail["photo"]

        results = await asyncio.gather(
            *[enrich_one(p) for p in targets], return_exceptions=True
        )
        failures = sum(1 for r in results if isinstance(r, Exception))
        enriched = sum(1 for p in targets if p.get("location"))
        print(f"📍 景点详情补全: {enriched}/{len(targets)} 拿到坐标"
              + (f"，{failures} 个异常" if failures else ""))

    async def _persist(self, city: str, pois: list[dict[str, Any]]) -> int:
        normalized = [p for p in (_normalize_poi(city, poi) for poi in pois) if p]
        if not normalized:
            return 0

        async with self.session_factory() as session:
            written = 0
            for item in normalized:
                stmt = insert(AttractionCache).values(**item)
                update_values = {
                    "poi_id": stmt.excluded.poi_id,
                    "address": stmt.excluded.address,
                    "longitude": stmt.excluded.longitude,
                    "latitude": stmt.excluded.latitude,
                    "amap_type": stmt.excluded.amap_type,
                    "category": stmt.excluded.category,
                    "rating": stmt.excluded.rating,
                    "ticket_price": stmt.excluded.ticket_price,
                    "image_url": stmt.excluded.image_url,
                    "last_updated": datetime.utcnow(),
                }
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["city", "name"],
                        set_=update_values,
                    )
                )
                written += 1
            await session.commit()
            return written


_service: Optional[AttractionsCacheService] = None


def get_attractions_cache_service() -> AttractionsCacheService:
    global _service
    if _service is None:
        _service = AttractionsCacheService()
    return _service
