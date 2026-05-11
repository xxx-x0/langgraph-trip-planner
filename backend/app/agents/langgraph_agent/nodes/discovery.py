"""景点发现阶段的专用节点 — 用于 Discovery Graph"""

import re
import json
from typing import Dict, Any, List

from langchain_core.messages import SystemMessage, HumanMessage

from ..exceptions import _invoke_llm_with_retry, _invoke_tool_with_retry, NonRetryableError
from ..prompts import EXTRACT_ATTRACTIONS_PROMPT
from ..state import DiscoveryState
from ..utils.parsing import _extract_poi_names
from ....services.langchain_amap_tools import get_langchain_amap_service
from ....services.llm_service import get_llm


EXTRACT_ATTRACTIONS_DISCOVERY_PROMPT = """你是景点筛选专家。你的任务是从旅游攻略搜索结果中，提取搜索结果文本中明确提到的景点名称。

**核心规则:**
1. 你只能提取搜索结果文本中**明确写出名称**的景点
2. **禁止**根据城市名推测或补充搜索结果中没有提到的景点
3. **禁止**根据常识添加景点，即使你知道该城市有哪些著名景点
4. 如果搜索结果中提到了某个景点（即使只提到一次），也应该提取出来
5. 仔细阅读每一条搜索结果，不要遗漏任何被提及的景点

**提取规则:**
1. 只提取搜索结果文本中明确出现的景点名称
2. 优先提取被多次提及的景点（说明知名度高、代表性强）
3. 每个景点需要提取: 名称(name)、简短推荐理由(description)、景点类别(category)
4. 提取数量上限: 最多提取{max_count}个景点，为用户提供充足的选择余地。但不要为了凑数而添加搜索结果中未提到的景点
5. 景点类型判断（根据用户偏好灵活判断）:
   - 默认情况: 排除纯餐饮、纯住宿场所
   - 用户偏好包含"购物"时: 知名商场/商业综合体可作为景点提取
   - 用户偏好包含"美食"时: 知名美食街/夜市可作为景点提取
   - 用户偏好包含"文化"/"历史"时: 博物馆、纪念馆、古迹优先提取
   - 用户偏好包含"自然"/"户外"时: 公园、山岳、湖泊优先提取
6. 如果搜索结果中提到了门票价格、开放时间等实用信息，也一并提取到description中
7. category请从以下选项中选择: 自然风光、历史文化、现代都市、休闲娱乐、购物、美食街区、亲子、宗教、其他

**输出格式:**
请严格按照以下JSON格式返回:
```json
[
  {{"name": "故宫博物院", "description": "中国最大的古代宫殿建筑群，世界文化遗产，门票60元", "category": "历史文化"}},
  {{"name": "天坛公园", "description": "明清两代皇帝祭天之地，世界文化遗产", "category": "历史文化"}}
]
```

**注意:**
1. 必须返回JSON数组格式
2. 景点名称必须使用搜索结果中出现的名称，不要修改或简写
3. description应简洁但包含关键信息
4. 如果搜索结果中没有明确的景点信息，返回空数组[]
5. 请仔细遍历所有搜索结果，确保不遗漏任何被提及的景点
"""


async def extract_attractions_expanded_node(state: DiscoveryState) -> Dict[str, Any]:
    """从搜索结果中提取大量景点（20-40个），供用户选择"""
    print("🧠 执行节点: extract_attractions_expanded_node (发现模式)")
    raw_results = state.get("raw_search_results", "")
    request = state["request"]

    if not raw_results:
        print("⚠️ extract_attractions_expanded: 搜索结果为空，降级到高德搜索")
        try:
            service = get_langchain_amap_service()
            search_tool = await service.get_tool("maps_text_search")
            if search_tool:
                keywords = request.preferences[0] if request.preferences else "景点"
                fallback_result = await _invoke_tool_with_retry(
                    search_tool,
                    {"keywords": keywords, "city": request.city},
                    max_retries=2,
                    per_attempt_timeout=15.0,
                )
                fallback_pois = _extract_poi_names(str(fallback_result))
                extracted = [
                    {"name": p["name"], "description": p.get("address", ""), "category": "景点"}
                    for p in fallback_pois if p.get("name")
                ]
                return {"extracted_pois": extracted}
        except Exception as e:
            print(f"⚠️ 降级高德搜索也失败: {e}")
        return {
            "extracted_pois": [],
            "errors": ["extract_attractions_expanded: 搜索结果为空且降级搜索失败"],
        }

    try:
        llm = get_llm()
        travel_days = request.travel_days
        max_count = min(40, max(20, travel_days * 6))
        preferences = request.preferences or []
        pref_hint = f"\n用户偏好: {', '.join(preferences)}" if preferences else "\n用户无特殊偏好（按通用景点提取）"

        prompt_template = EXTRACT_ATTRACTIONS_DISCOVERY_PROMPT.format(max_count=max_count)
        prompt = f"旅行天数: {travel_days}天，最多提取{max_count}个景点。{pref_hint}\n\n以下是搜索结果:\n{raw_results[:20000]}"
        response = await _invoke_llm_with_retry(
            llm,
            [SystemMessage(content=prompt_template), HumanMessage(content=prompt)],
            max_retries=2,
            per_attempt_timeout=45.0,
        )

        content = response.content.strip()

        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif "[" in content:
            json_start = content.find("[")
            json_end = content.rfind("]") + 1
            json_str = content[json_start:json_end]
        else:
            raise ValueError("响应中未找到JSON")

        pois = json.loads(json_str)
        if not isinstance(pois, list):
            pois = []

        valid_pois = []
        for poi in pois:
            if isinstance(poi, dict) and poi.get("name"):
                valid_pois.append({
                    "name": poi["name"],
                    "description": poi.get("description", ""),
                    "category": poi.get("category", "景点"),
                })

        print(f"🧠 LLM提取到 {len(valid_pois)} 个景点: {[p['name'] for p in valid_pois]}")

        min_attractions = max(10, travel_days * 3)
        if len(valid_pois) < min_attractions:
            print(f"⚠️ 景点数量不足({len(valid_pois)} < {min_attractions})，尝试用高德搜索补充...")
            try:
                service = get_langchain_amap_service()
                search_tool = await service.get_tool("maps_text_search")
                if search_tool:
                    existing_names = {p["name"] for p in valid_pois}
                    search_keywords = ["景点", "旅游"] + (preferences[:2] if preferences else [])
                    for kw in search_keywords:
                        if len(valid_pois) >= min_attractions:
                            break
                        fallback_result = await _invoke_tool_with_retry(
                            search_tool,
                            {"keywords": kw, "city": request.city},
                            max_retries=2,
                            per_attempt_timeout=15.0,
                        )
                        extra_pois = _extract_poi_names(str(fallback_result))
                        for poi in extra_pois:
                            if poi.get("name") and poi["name"] not in existing_names:
                                valid_pois.append({
                                    "name": poi["name"],
                                    "description": poi.get("address", "") or "高德推荐景点",
                                    "category": "景点",
                                })
                                existing_names.add(poi["name"])
                                if len(valid_pois) >= min_attractions:
                                    break
                    print(f"  ✅ 补充后共 {len(valid_pois)} 个景点")
            except Exception as e:
                print(f"  ⚠️ 高德补充搜索失败: {e}")

        return {"extracted_pois": valid_pois}
    except Exception as e:
        print(f"❌ extract_attractions_expanded_node 异常: {e}")
        return {
            "extracted_pois": [],
            "errors": [f"extract_attractions_expanded: 提取失败 - {str(e)[:200]}"],
        }


async def geocode_dispatch_node(state: DiscoveryState) -> Dict[str, Any]:
    """将提取的景点分成批次，供 geocode_batch_node 循环处理"""
    extracted_pois = state.get("extracted_pois", [])
    batch_size = 5
    batches = [extracted_pois[i:i + batch_size] for i in range(0, len(extracted_pois), batch_size)]
    print(f"📍 geocode_dispatch: 将 {len(extracted_pois)} 个景点分成 {len(batches)} 批 (每批 {batch_size} 个)")
    return {"_geocode_batches": batches}


async def geocode_batch_node(state: DiscoveryState) -> Dict[str, Any]:
    """处理一批景点的地理编码，然后返回结果并更新剩余批次"""
    batches = state.get("_geocode_batches", [])
    if not batches:
        return {"discovered_attractions": [], "_geocode_batches": []}

    current_batch = batches[0]
    remaining = batches[1:]
    request = state["request"]

    batch_idx = len(state.get("discovered_attractions", [])) // 5 + 1
    print(f"📍 geocode_batch #{batch_idx}: 处理 {len(current_batch)} 个景点...")

    try:
        service = get_langchain_amap_service()
        search_tool = await service.get_tool("maps_text_search")
        detail_tool = await service.get_tool("maps_search_detail")

        results = []

        for poi in current_batch:
            name = poi["name"]
            description = poi.get("description", "")
            category = poi.get("category", "景点")
            attraction = {
                "name": name,
                "description": description,
                "category": category,
                "address": "",
                "rating": None,
                "ticket_price": None,
                "image_url": None,
                "location": None,
                "poi_id": None,
            }

            for attempt_name in [name, re.sub(r'(风景名胜区|风景区|景区|旅游区|度假区|步行街|商业街)$', '', name)]:
                if not attempt_name:
                    continue
                try:
                    search_result = await _invoke_tool_with_retry(
                        search_tool,
                        {"keywords": attempt_name, "city": request.city},
                        max_retries=2,
                        per_attempt_timeout=15.0,
                    )
                    result_str = str(search_result)
                    poi_list = _extract_poi_names(result_str)

                    if poi_list:
                        best_poi = poi_list[0]
                        attraction["address"] = best_poi.get("address", "")
                        attraction["poi_id"] = best_poi.get("id")

                        if best_poi.get("location"):
                            loc = best_poi["location"]
                            if isinstance(loc, str) and "," in loc:
                                lng, lat = loc.split(",")
                                attraction["location"] = {"longitude": float(lng), "latitude": float(lat)}
                            elif isinstance(loc, dict):
                                attraction["location"] = loc

                        if best_poi.get("rating"):
                            try:
                                attraction["rating"] = float(best_poi["rating"])
                            except (ValueError, TypeError):
                                pass

                        if best_poi.get("cost"):
                            attraction["ticket_price"] = str(best_poi["cost"])

                        if best_poi.get("photo"):
                            attraction["image_url"] = best_poi["photo"]

                        if detail_tool and best_poi.get("id"):
                            try:
                                detail_result = await _invoke_tool_with_retry(
                                    detail_tool,
                                    {"id": best_poi["id"]},
                                    max_retries=1,
                                    per_attempt_timeout=10.0,
                                )
                                detail_str = str(detail_result)
                                detail_data = _extract_poi_names(detail_str)
                                if detail_data:
                                    d = detail_data[0]
                                    if d.get("address") and not attraction["address"]:
                                        attraction["address"] = d["address"]
                                    if d.get("rating") and not attraction["rating"]:
                                        try:
                                            attraction["rating"] = float(d["rating"])
                                        except (ValueError, TypeError):
                                            pass
                                    if d.get("cost") and not attraction["ticket_price"]:
                                        attraction["ticket_price"] = str(d["cost"])
                                    if d.get("photo") and not attraction["image_url"]:
                                        attraction["image_url"] = d["photo"]
                                    if d.get("location") and not attraction["location"]:
                                        loc = d["location"]
                                        if isinstance(loc, str) and "," in loc:
                                            lng, lat = loc.split(",")
                                            attraction["location"] = {"longitude": float(lng), "latitude": float(lat)}
                            except Exception as e:
                                print(f"  ⚠️ 详情查询失败({name}): {e}")

                        print(f"  ✅ 发现景点: {name} (坐标: {'有' if attraction['location'] else '无'})")
                        break
                except Exception as e:
                    print(f"  ⚠️ 搜索景点{attempt_name}失败: {e}")

            results.append(attraction)

        print(f"📍 batch #{batch_idx} 完成: {len(results)} 个景点, 剩余 {len(remaining)} 批")
        return {"discovered_attractions": results, "_geocode_batches": remaining}
    except Exception as e:
        print(f"❌ geocode_batch_node 异常: {e}")
        return {
            "discovered_attractions": [],
            "_geocode_batches": remaining,
            "errors": [f"geocode_batch: 地理编码失败 - {str(e)[:200]}"],
        }


async def gather_discovery_node(state: DiscoveryState) -> Dict[str, Any]:
    """发现阶段的汇总节点"""
    print("🔗 执行节点: gather_discovery_node (发现阶段汇总)")
    discovered = state.get("discovered_attractions", [])
    weather = state.get("weather_info", "")
    errors = state.get("errors", [])

    with_location = sum(1 for a in discovered if a.get("location"))
    print(f"📊 发现阶段汇总: {len(discovered)} 个景点 ({with_location} 个有坐标), "
          f"天气: {'有' if weather else '无'}")

    if errors:
        print(f"🚨 发现阶段共 {len(errors)} 个错误")
        for err in errors[-5:]:
            print(f"   - {err[:200]}")

    return {}
