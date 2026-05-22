import re
from typing import Dict, Any

from langchain_core.messages import HumanMessage

from ..exceptions import _invoke_tool_with_retry, _invoke_llm_with_retry
from ..state import TripPlannerState
from ..utils.geo import (
    _extract_coordinates_regex,
    _haversine_distance,
    _cluster_attractions_by_proximity,
    _order_cluster_by_tsp,
    _select_top_attractions,
    _format_cluster_info,
)
from ..utils.parsing import _extract_json_array, _extract_poi_names
from ..nodes.search import _extract_must_visit_attractions, analyze_free_text
from ....services.langchain_amap_tools import get_langchain_amap_service
from ....services.llm_service import get_llm


async def cluster_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    print("🗺️ 执行节点: cluster_attractions_node")

    if state.get("cluster_info"):
        print("  ⏭️ 聚类已完成，跳过重复执行")
        return {}

    attractions_info = state.get("attractions_info", "")
    request = state["request"]

    must_visit = _extract_must_visit_attractions(request.free_text_input or "")
    analysis = await analyze_free_text(request.free_text_input or "")
    must_visit = analysis.get("attractions", [])
    if must_visit:
        print(f"🎯 用户指定必游景点: {must_visit}")

    valid_attractions = _extract_coordinates_regex(attractions_info)
    if valid_attractions:
        print(f"📊 正则提取到 {len(valid_attractions)} 个景点坐标（跳过LLM提取）")
    else:
        poi_list = _extract_poi_names(attractions_info)
        if poi_list:
            service = get_langchain_amap_service()
            detail_tool = await service.get_tool("maps_search_detail")
            geo_tool = await service.get_tool("maps_geo")

            pois_with_id = [p for p in poi_list if p.get("id")]
            pois_without_id = [p for p in poi_list if not p.get("id")]

            if pois_with_id and detail_tool:
                print(f"📊 从POI数据提取到 {len(pois_with_id)} 个有ID的景点，优先使用 maps_search_detail 获取坐标...")
                for poi in pois_with_id[:20]:
                    try:
                        detail_result = await _invoke_tool_with_retry(detail_tool, {"id": poi["id"]})
                        result_str = str(detail_result)
                        loc_match = re.search(r'"location"\s*:\s*"([\d.]+)\s*,\s*([\d.]+)"', result_str)
                        if not loc_match:
                            loc_match = re.search(r'"longitude"?\s*[:=]\s*["\']?([\d.]+).*?"latitude"?\s*[:=]\s*["\']?([\d.]+)', result_str, re.DOTALL)
                        if not loc_match:
                            loc_match = re.search(r'([\d.]{6,12})\s*,\s*([\d.]{6,12})', result_str)
                        if loc_match:
                            lon = float(loc_match.group(1))
                            lat = float(loc_match.group(2))
                            if 73 < lon < 136 and 3 < lat < 54:
                                valid_attractions.append({"name": poi["name"], "longitude": lon, "latitude": lat})
                                continue
                        print(f"  ⚠️ maps_search_detail[{poi['id']}]未提取到坐标，将降级到maps_geo")
                    except Exception as e:
                        print(f"  ⚠️ maps_search_detail查询{poi['name']}失败: {e}")

                if valid_attractions:
                    print(f"📊 maps_search_detail获取到 {len(valid_attractions)} 个景点坐标")

            failed_pois = [p for p in pois_with_id if p["name"] not in {a["name"] for a in valid_attractions}]
            all_geo_pois = failed_pois + pois_without_id

            if all_geo_pois and geo_tool:
                print(f"📊 对 {len(all_geo_pois)} 个景点使用 maps_geo 补查坐标...")
                geo_count_before = len(valid_attractions)
                for poi in all_geo_pois[:20]:
                    try:
                        geo_result = await _invoke_tool_with_retry(geo_tool, {"address": poi["name"], "city": request.city})
                        result_str = str(geo_result)
                        loc_match = re.search(r'"location"\s*:\s*"([\d.]+)\s*,\s*([\d.]+)"', result_str)
                        if not loc_match:
                            loc_match = re.search(r'([\d.]+)\s*,\s*([\d.]+)', result_str)
                        if loc_match:
                            lon = float(loc_match.group(1))
                            lat = float(loc_match.group(2))
                            if 73 < lon < 136 and 3 < lat < 54:
                                valid_attractions.append({"name": poi["name"], "longitude": lon, "latitude": lat})
                    except Exception as e:
                        print(f"  ⚠️ maps_geo查询{poi['name']}失败: {e}")
                geo_added = len(valid_attractions) - geo_count_before
                if geo_added > 0:
                    print(f"📊 maps_geo补充获取到 {geo_added} 个景点坐标")

            if valid_attractions:
                print(f"📊 坐标查询完成: 共获取到 {len(valid_attractions)} 个景点坐标")
            else:
                print(f"⚠️ maps_search_detail 和 maps_geo 均未获取到坐标")

        if not valid_attractions:
            print(f"📊 正则未提取到坐标，数据前500字符: {attractions_info[:500]}")
            print("📊 尝试LLM提取...")
            llm = get_llm()
            extract_prompt = f"""从以下景点搜索结果中，提取所有景点的名称和经纬度坐标。
请以JSON数组格式返回，每个元素包含 name, longitude, latitude 三个字段。longitude和latitude必须是浮点数。

**重要**: 中国的经度范围约73-136，纬度范围约3-54。请确保提取的坐标在此范围内。

搜索结果:
{attractions_info[:4000]}

请直接返回JSON数组，不要包含其他文字。示例:
[{{"name": "故宫博物院", "longitude": 116.3974, "latitude": 39.9165}}]"""

            try:
                response = await _invoke_llm_with_retry(llm, [HumanMessage(content=extract_prompt)])
                attractions_list = _extract_json_array(response.content)

                if attractions_list:
                    valid_attractions = [
                        a for a in attractions_list
                        if isinstance(a.get("longitude"), (int, float)) and isinstance(a.get("latitude"), (int, float))
                        and 73 < a["longitude"] < 136 and 3 < a["latitude"] < 54
                    ]

                if not valid_attractions:
                    print("⚠️ LLM提取也失败，尝试从原始文本正则提取...")
                    valid_attractions = _extract_coordinates_regex(response.content)
            except Exception as e:
                print(f"⚠️ LLM坐标提取异常: {e}")

    if not valid_attractions:
        print("⚠️ 未能提取有效景点坐标，跳过聚类")
        return {"cluster_info": "景点坐标提取失败，请根据景点信息自行合理分配每日行程。", "clusters_data": []}

    print(f"📊 成功提取 {len(valid_attractions)} 个景点坐标")

    n = len(valid_attractions)
    dist_matrix = [[0.0] * n for _ in range(n)]

    distance_tool = None
    try:
        service = get_langchain_amap_service()
        distance_tool = await service.get_tool("maps_distance")
    except Exception:
        pass

    if distance_tool:
        print(f"📊 使用 maps_distance 批量查询驾车距离（{n}个景点）...")
        try:
            for i in range(n):
                destination = f"{valid_attractions[i]['longitude']},{valid_attractions[i]['latitude']}"
                origins_parts = []
                origin_indices = []
                for j in range(n):
                    if j != i:
                        origins_parts.append(f"{valid_attractions[j]['longitude']},{valid_attractions[j]['latitude']}")
                        origin_indices.append(j)
                origins = "|".join(origins_parts)

                try:
                    distance_result = await _invoke_tool_with_retry(
                        distance_tool,
                        {"origins": origins, "destination": destination, "type": "1"},
                        max_retries=2,
                        per_attempt_timeout=15.0,
                    )
                except Exception as e:
                    print(f"  ⚠️ maps_distance 调用失败(起点{i}): {e}")
                    continue

                result_str = str(distance_result)
                if i == 0:
                    print(f"  📋 maps_distance 返回样例(前300字符): {result_str[:300]}")

                try:
                    import json
                    import ast
                    parsed = result_str
                    if isinstance(parsed, str):
                        for _ in range(2):
                            try:
                                parsed = json.loads(parsed)
                                break
                            except json.JSONDecodeError:
                                try:
                                    parsed = ast.literal_eval(parsed)
                                    break
                                except (ValueError, SyntaxError):
                                    pass

                    if isinstance(parsed, list) and len(parsed) > 0:
                        first = parsed[0]
                        if isinstance(first, dict) and "text" in first:
                            inner = first["text"]
                            if isinstance(inner, str):
                                try:
                                    parsed = json.loads(inner)
                                except json.JSONDecodeError:
                                    try:
                                        parsed = ast.literal_eval(inner)
                                    except (ValueError, SyntaxError):
                                        pass

                    results_list = []
                    if isinstance(parsed, dict):
                        results_list = parsed.get("results", [])
                        if not results_list:
                            for key in parsed:
                                val = parsed[key]
                                if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                                    results_list = val
                                    break
                    elif isinstance(parsed, list):
                        if len(parsed) > 0 and isinstance(parsed[0], dict) and "results" in parsed[0]:
                            results_list = parsed[0]["results"]
                        else:
                            results_list = parsed

                    for idx, origin_j in enumerate(origin_indices):
                        if idx < len(results_list):
                            dist_info = results_list[idx]
                            dist_val = dist_info.get("distance", 0) if isinstance(dist_info, dict) else 0
                            if dist_val:
                                try:
                                    dist_val = int(dist_val)
                                except (ValueError, TypeError):
                                    dist_val = 0
                                if dist_val > 0:
                                    dist_km = dist_val / 1000.0
                                    dist_matrix[i][origin_j] = dist_km
                                    dist_matrix[origin_j][i] = dist_km
                except (json.JSONDecodeError, TypeError, KeyError, IndexError) as e:
                    print(f"  ⚠️ maps_distance 结果解析失败(起点{i}): {e}")

            missing = 0
            for i in range(n):
                for j in range(i + 1, n):
                    if dist_matrix[i][j] == 0.0:
                        missing += 1
                        d = _haversine_distance(
                            valid_attractions[i]["latitude"], valid_attractions[i]["longitude"],
                            valid_attractions[j]["latitude"], valid_attractions[j]["longitude"]
                        )
                        dist_matrix[i][j] = d
                        dist_matrix[j][i] = d
            if missing > 0:
                print(f"  ⚠️ {missing} 对景点距离缺失，已用直线距离补充")
            print(f"📊 maps_distance 距离矩阵构建完成")
        except Exception as e:
            print(f"⚠️ maps_distance 批量查询失败，降级到直线距离: {e}")
            for i in range(n):
                for j in range(i + 1, n):
                    d = _haversine_distance(
                        valid_attractions[i]["latitude"], valid_attractions[i]["longitude"],
                        valid_attractions[j]["latitude"], valid_attractions[j]["longitude"]
                    )
                    dist_matrix[i][j] = d
                    dist_matrix[j][i] = d
    else:
        print(f"📊 maps_distance 不可用，使用直线距离计算...")
        for i in range(n):
            for j in range(i + 1, n):
                d = _haversine_distance(
                    valid_attractions[i]["latitude"], valid_attractions[i]["longitude"],
                    valid_attractions[j]["latitude"], valid_attractions[j]["longitude"]
                )
                dist_matrix[i][j] = d
                dist_matrix[j][i] = d

    clusters = _cluster_attractions_by_proximity(valid_attractions, request.travel_days)

    for i in range(len(clusters)):
        clusters[i] = _order_cluster_by_tsp(clusters[i])

    trimmed = False
    total_attractions = sum(len(c) for c in clusters)
    max_per_day = 3
    if total_attractions > request.travel_days * max_per_day:
        print(f"✂️ 景点数量({total_attractions})超过上限({request.travel_days * max_per_day})，开始筛选...")
        must_visit_names = set(must_visit)
        if must_visit_names:
            must_visit_attractions = []
            other_attractions = []
            for attr in valid_attractions:
                if any(mv in attr["name"] or attr["name"] in mv for mv in must_visit_names):
                    must_visit_attractions.append(attr)
                else:
                    other_attractions.append(attr)
            if len(must_visit_attractions) < len(valid_attractions):
                print(f"🎯 保护用户指定景点: {[a['name'] for a in must_visit_attractions]}")
                clusters = _cluster_attractions_by_proximity(valid_attractions, request.travel_days)
                for i in range(len(clusters)):
                    clusters[i] = _order_cluster_by_tsp(clusters[i])
                protected_names = {a["name"] for a in must_visit_attractions}
                for ci in range(len(clusters)):
                    new_cluster = []
                    for attr in clusters[ci]:
                        if attr["name"] in protected_names:
                            new_cluster.append(attr)
                        elif len(new_cluster) < max_per_day:
                            has_protected = any(a["name"] in protected_names for a in new_cluster)
                            if has_protected and len(new_cluster) < max_per_day:
                                new_cluster.append(attr)
                            elif not has_protected and len(new_cluster) < max_per_day:
                                new_cluster.append(attr)
                    clusters[ci] = new_cluster
                trimmed = True
            else:
                clusters = _select_top_attractions(clusters, max_per_day)
                trimmed = True
        else:
            clusters = _select_top_attractions(clusters, max_per_day)
            trimmed = True

    cluster_info = _format_cluster_info(clusters, valid_attractions, dist_matrix, trimmed)

    try:
        regeocode_tool = await service.get_tool("maps_regeocode")
    except Exception:
        regeocode_tool = None

    if regeocode_tool:
        enriched_count = 0
        for attr in valid_attractions:
            if not attr.get("address") and attr.get("longitude") and enriched_count < 10:
                try:
                    location_str = f"{attr['longitude']},{attr['latitude']}"
                    rg_result = await _invoke_tool_with_retry(
                        regeocode_tool,
                        {"location": location_str},
                        per_attempt_timeout=10.0,
                    )
                    rg_str = str(rg_result)
                    try:
                        import json
                        rg_parsed = json.loads(rg_str) if isinstance(rg_str, str) else rg_str
                        if isinstance(rg_parsed, str):
                            rg_parsed = json.loads(rg_parsed)
                        if isinstance(rg_parsed, dict):
                            addr = rg_parsed.get("formatted_address", "")
                            if not addr:
                                poi_list = rg_parsed.get("pois", [])
                                if poi_list:
                                    addr = poi_list[0].get("name", "")
                            if addr:
                                attr["address"] = addr
                                enriched_count += 1
                    except (json.JSONDecodeError, TypeError):
                        pass
                except Exception:
                    pass
        if enriched_count > 0:
            print(f"📊 maps_regeocode 为 {enriched_count} 个景点补充了地址")
            cluster_info = _format_cluster_info(clusters, valid_attractions, dist_matrix, trimmed)

    final_count = sum(len(c) for c in clusters)
    print(f"✅ 景点聚类完成: {len(valid_attractions)} 个景点 → 筛选后 {final_count} 个，分为 {len(clusters)} 组")

    return {"cluster_info": cluster_info, "clusters_data": clusters}


async def cluster_from_selections_node(state: TripPlannerState) -> Dict[str, Any]:
    """基于用户选择的景点进行聚类（结构化输入，已有坐标）"""
    print("🗺️ 执行节点: cluster_from_selections_node")

    selected_attractions = state.get("user_selected_attractions", [])
    day_assignments = state.get("user_day_assignments")
    request = state["request"]

    if not selected_attractions:
        return {"cluster_info": "未选择任何景点，无法生成行程。", "clusters_data": []}

    if day_assignments:
        print(f"📊 使用用户自定义日程分配: {len(day_assignments)} 天")
        clusters = []
        for day_attrs in day_assignments:
            day_cluster = []
            for attr in day_attrs:
                loc = attr.get("location")
                if loc:
                    day_cluster.append({
                        "name": attr["name"],
                        "longitude": loc.get("longitude", 0),
                        "latitude": loc.get("latitude", 0),
                    })
                else:
                    day_cluster.append({"name": attr["name"], "longitude": 0, "latitude": 0})
            clusters.append(day_cluster)
    else:
        valid_attractions = []
        for attr in selected_attractions:
            loc = attr.get("location")
            if loc and loc.get("longitude") and loc.get("latitude"):
                valid_attractions.append({
                    "name": attr["name"],
                    "longitude": loc["longitude"],
                    "latitude": loc["latitude"],
                })

        if not valid_attractions:
            names = [a["name"] for a in selected_attractions]
            simple_info = "\n".join([f"第{i+1}天: {name}" for i, name in enumerate(names)])
            return {"cluster_info": f"景点坐标缺失，按选择顺序分配:\n{simple_info}", "clusters_data": []}

        n = len(valid_attractions)
        dist_matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                d = _haversine_distance(
                    valid_attractions[i]["latitude"], valid_attractions[i]["longitude"],
                    valid_attractions[j]["latitude"], valid_attractions[j]["longitude"]
                )
                dist_matrix[i][j] = d
                dist_matrix[j][i] = d

        clusters = _cluster_attractions_by_proximity(valid_attractions, request.travel_days)
        for i in range(len(clusters)):
            clusters[i] = _order_cluster_by_tsp(clusters[i])

        valid_attractions_for_format = valid_attractions

    all_attrs = []
    for c in clusters:
        all_attrs.extend(c)
    n = len(all_attrs)
    dist_matrix_final = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if all_attrs[i].get("longitude") and all_attrs[j].get("longitude"):
                d = _haversine_distance(
                    all_attrs[i]["latitude"], all_attrs[i]["longitude"],
                    all_attrs[j]["latitude"], all_attrs[j]["longitude"]
                )
                dist_matrix_final[i][j] = d
                dist_matrix_final[j][i] = d

    cluster_info = _format_cluster_info(clusters, all_attrs, dist_matrix_final, False)

    # 同时构建 attractions_info 供下游节点使用
    attractions_info_parts = []
    for attr in selected_attractions:
        parts = [f"名称: {attr['name']}"]
        if attr.get("address"):
            parts.append(f"地址: {attr['address']}")
        if attr.get("location"):
            loc = attr["location"]
            parts.append(f"坐标: {loc.get('longitude', '')},{loc.get('latitude', '')}")
        if attr.get("category"):
            parts.append(f"类别: {attr['category']}")
        if attr.get("rating"):
            parts.append(f"评分: {attr['rating']}")
        if attr.get("ticket_price"):
            parts.append(f"门票: {attr['ticket_price']}")
        if attr.get("description"):
            parts.append(f"简介: {attr['description']}")
        if attr.get("visit_minutes"):
            parts.append(f"预计游玩: {attr['visit_minutes']}min")
        attractions_info_parts.append(" | ".join(parts))

    attractions_info = "\n".join(attractions_info_parts)

    final_count = sum(len(c) for c in clusters)
    print(f"✅ 用户选择景点聚类完成: {len(selected_attractions)} 个选中 → {final_count} 个分为 {len(clusters)} 组")

    return {"cluster_info": cluster_info, "attractions_info": attractions_info, "clusters_data": clusters}
