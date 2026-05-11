import os
from typing import Dict, Any, Optional, List

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from .exceptions import RetryableError
from .state import TripPlannerState, DiscoveryState
from .nodes import (
    web_search_attractions_node,
    extract_attractions_node,
    geocode_attractions_node,
    search_weather_node,
    search_hotel_node,
    gather_search_node,
    search_food_node,
    cluster_attractions_node,
    cluster_from_selections_node,
    plan_route_node,
    generate_plan_node,
    macro_planner_node,
    reduce_assemble_node,
    global_synthesizer_node,
    day_plan_subgraph_node,
    load_user_preferences_node,
    extract_preferences_node,
    save_preferences_node,
    extract_attractions_expanded_node,
    geocode_dispatch_node,
    geocode_batch_node,
    gather_discovery_node,
)
from .utils.parsing import _create_fallback_plan
from ...services.llm_service import get_llm
from ...services.langchain_amap_tools import get_mcp_tools


async def error_handler_node(state: TripPlannerState) -> Dict[str, Any]:
    errors = state.get("errors", [])
    if errors:
        print(f"🚨 错误处理器: 检测到 {len(errors)} 个错误")
        for err in errors[-5:]:
            print(f"   - {err[:200]}")
    return {}


def _route_after_gather(state: TripPlannerState) -> str:
    errors = state.get("errors", [])
    attractions = state.get("attractions_info", "")
    critical_errors = [e for e in errors if ("web_search_attractions" in e or "extract_attractions" in e or "geocode_attractions" in e) and "不可重试" in e]
    if critical_errors and not attractions:
        print("🚨 景点搜索完全失败且不可重试，路由到错误处理器")
        return "error_handler"
    return "cluster_attractions"


def _route_to_day_plans(state: TripPlannerState) -> List[Send]:
    macro_plan = state.get("macro_plan")
    if not macro_plan:
        print("⚠️ macro_plan为空，无法派发单日子图")
        return []

    sends = []
    request = state.get("request")
    food_pref = request.food_preference if request else "本地特色"
    for day_skeleton in macro_plan.days:
        sends.append(Send(
            "day_plan_subgraph",
            {
                "day_index": day_skeleton.day_index,
                "date": day_skeleton.date,
                "attraction_names": day_skeleton.attraction_names,
                "hotel_name": day_skeleton.hotel_name,
                "city": macro_plan.city,
                "transportation": macro_plan.transportation,
                "accommodation": macro_plan.accommodation,
                "attractions_info": state.get("attractions_info", ""),
                "hotels_info": state.get("hotels_info", ""),
                "food_info": state.get("food_info", ""),
                "route_info": state.get("route_info", ""),
                "weather_info": state.get("weather_info", ""),
                "cluster_info": state.get("cluster_info", ""),
                "route_segments_data": [],
                "day_plan": None,
                "retry_count": 0,
                "max_retries": 3,
                "last_error": "",
                "day_plans": [],
                "day_food_info": "",
                "food_preference": food_pref,
            }
        ))
    print(f"📤 Send API 派发 {len(sends)} 个单日子图")
    return sends


def create_trip_planner_graph():
    from langgraph.types import RetryPolicy

    workflow = StateGraph(TripPlannerState)

    search_retry = RetryPolicy(
        max_attempts=2,
        initial_interval=1.0,
        backoff_factor=2.0,
        retry_on=lambda e: isinstance(e, RetryableError),
    )

    workflow.add_node("load_user_preferences", load_user_preferences_node)
    workflow.add_node("web_search_attractions", web_search_attractions_node, retry=search_retry)
    workflow.add_node("extract_attractions", extract_attractions_node, retry=search_retry)
    workflow.add_node("geocode_attractions", geocode_attractions_node, retry=search_retry)
    workflow.add_node("search_weather", search_weather_node, retry=search_retry)
    workflow.add_node("search_hotel", search_hotel_node, retry=search_retry)
    workflow.add_node("gather_search", gather_search_node)
    workflow.add_node("error_handler", error_handler_node)
    workflow.add_node("cluster_attractions", cluster_attractions_node)
    workflow.add_node("search_food", search_food_node)
    workflow.add_node("plan_route", plan_route_node)
    workflow.add_node("macro_planner", macro_planner_node)
    workflow.add_node("reduce_assemble", reduce_assemble_node)
    workflow.add_node("global_synthesizer", global_synthesizer_node)
    workflow.add_node("extract_preferences", extract_preferences_node)
    workflow.add_node("save_preferences", save_preferences_node)
    workflow.add_node("day_plan_subgraph", day_plan_subgraph_node)

    workflow.add_edge(START, "web_search_attractions")
    workflow.add_edge(START, "search_weather")
    workflow.add_edge(START, "search_hotel")

    workflow.add_edge("web_search_attractions", "extract_attractions")
    workflow.add_edge("extract_attractions", "geocode_attractions")

    workflow.add_edge(["geocode_attractions", "search_weather", "search_hotel"], "gather_search")

    workflow.add_conditional_edges(
        "gather_search",
        _route_after_gather,
        {
            "cluster_attractions": "cluster_attractions",
            "error_handler": "error_handler",
        },
    )
    workflow.add_edge("error_handler", "cluster_attractions")

    workflow.add_edge("cluster_attractions", "search_food")
    workflow.add_edge("search_food", "plan_route")
    workflow.add_edge("plan_route", "macro_planner")
    workflow.add_conditional_edges(
        "macro_planner",
        _route_to_day_plans,
        ["day_plan_subgraph"]
    )
    workflow.add_edge("day_plan_subgraph", "reduce_assemble")
    workflow.add_edge("reduce_assemble", "global_synthesizer")
    workflow.add_edge("global_synthesizer", "extract_preferences")

    workflow.add_edge("extract_preferences", "save_preferences")
    workflow.add_edge("save_preferences", END)

    app = workflow.compile()
    return app


def _route_after_geocode_batch(state) -> str:
    if state.get("_geocode_batches"):
        return "geocode_batch"
    return "gather_discovery"


def create_discovery_graph():
    """创建景点发现 Graph — 大量搜索景点并返回结构化数据供用户选择，分批流式输出"""
    from langgraph.types import RetryPolicy

    workflow = StateGraph(DiscoveryState)

    search_retry = RetryPolicy(
        max_attempts=2,
        initial_interval=1.0,
        backoff_factor=2.0,
        retry_on=lambda e: isinstance(e, RetryableError),
    )

    workflow.add_node("web_search_attractions", web_search_attractions_node, retry=search_retry)
    workflow.add_node("extract_attractions_expanded", extract_attractions_expanded_node, retry=search_retry)
    workflow.add_node("geocode_dispatch", geocode_dispatch_node)
    workflow.add_node("geocode_batch", geocode_batch_node, retry=search_retry)
    workflow.add_node("search_weather", search_weather_node, retry=search_retry)
    workflow.add_node("gather_discovery", gather_discovery_node)

    workflow.add_edge(START, "web_search_attractions")
    workflow.add_edge(START, "search_weather")

    workflow.add_edge("web_search_attractions", "extract_attractions_expanded")
    workflow.add_edge("extract_attractions_expanded", "geocode_dispatch")
    workflow.add_edge("geocode_dispatch", "geocode_batch")

    workflow.add_conditional_edges(
        "geocode_batch",
        _route_after_geocode_batch,
        {
            "geocode_batch": "geocode_batch",
            "gather_discovery": "gather_discovery",
        },
    )

    workflow.add_edge("search_weather", "gather_discovery")
    workflow.add_edge("gather_discovery", END)

    return workflow.compile()


def create_planning_graph():
    """创建基于用户选择的行程规划 Graph — 接收选中景点和日程分配，生成完整行程"""
    from langgraph.types import RetryPolicy

    search_retry = RetryPolicy(
        max_attempts=2,
        initial_interval=1.0,
        backoff_factor=2.0,
        retry_on=lambda e: isinstance(e, RetryableError),
    )

    workflow = StateGraph(TripPlannerState)

    workflow.add_node("cluster_from_selections", cluster_from_selections_node)
    workflow.add_node("search_food", search_food_node)
    workflow.add_node("search_hotel", search_hotel_node, retry=search_retry)
    workflow.add_node("plan_route", plan_route_node)
    workflow.add_node("macro_planner", macro_planner_node)
    workflow.add_node("reduce_assemble", reduce_assemble_node)
    workflow.add_node("global_synthesizer", global_synthesizer_node)
    workflow.add_node("extract_preferences", extract_preferences_node)
    workflow.add_node("save_preferences", save_preferences_node)
    workflow.add_node("day_plan_subgraph", day_plan_subgraph_node)

    workflow.add_edge(START, "cluster_from_selections")

    workflow.add_edge("cluster_from_selections", "search_food")
    workflow.add_edge("cluster_from_selections", "search_hotel")
    workflow.add_edge("cluster_from_selections", "plan_route")

    workflow.add_edge(["search_food", "search_hotel", "plan_route"], "macro_planner")

    workflow.add_conditional_edges(
        "macro_planner",
        _route_to_day_plans,
        ["day_plan_subgraph"]
    )
    workflow.add_edge("day_plan_subgraph", "reduce_assemble")
    workflow.add_edge("reduce_assemble", "global_synthesizer")
    workflow.add_edge("global_synthesizer", "extract_preferences")
    workflow.add_edge("extract_preferences", "save_preferences")
    workflow.add_edge("save_preferences", END)

    return workflow.compile()


class LangGraphTripPlanner:
    """基于 LangGraph 的旅行规划系统封装类"""

    def __init__(self):
        print("🔄 初始化 LangGraph 旅行规划系统...")
        self.app = create_trip_planner_graph()
        self.discovery_app = create_discovery_graph()
        self.planning_app = create_planning_graph()

    async def _pre_init_services(self):
        try:
            print("⏳ 预初始化 LLM 和 MCP 服务...")
            get_llm()
            await get_mcp_tools()
            print("✅ 服务预初始化完成")
        except Exception as e:
            print(f"⚠️ 服务预初始化失败: {e}")

    def _build_initial_state(self, request, user_id: str = "default"):
        return {
            "request": request,
            "attractions_info": "",
            "raw_search_results": "",
            "selected_pois": [],
            "weather_info": "",
            "hotels_info": "",
            "aigohotel_raw_results": "",
            "selected_hotels": [],
            "food_info": "",
            "cluster_info": "",
            "route_info": "",
            "trip_plan": None,
            "errors": [],
            "messages": [],
            "user_preferences": None,
            "extracted_preferences": None,
            "user_id": user_id,
            "macro_plan": None,
            "day_plans": [],
            "global_narrative": None,
            "user_selected_attractions": [],
            "user_day_assignments": None,
        }

    def _build_discovery_state(self, request, user_id: str = "default"):
        return {
            "request": request,
            "raw_search_results": "",
            "extracted_pois": [],
            "discovered_attractions": [],
            "weather_info": "",
            "errors": [],
            "messages": [],
            "user_id": user_id,
            "_geocode_batches": [],
        }

    def _build_planning_state(self, request, selected_attractions, day_assignments=None,
                               weather_info="", user_id="default"):
        state = self._build_initial_state(request, user_id)
        state["user_selected_attractions"] = selected_attractions
        state["user_day_assignments"] = day_assignments
        state["weather_info"] = weather_info
        return state

    async def discover_attractions_stream(self, request, user_id: str = "default"):
        """流式景点发现 — yield SSE 事件"""
        print(f"\n{'='*60}")
        print(f"🔍 开始景点发现...")
        print(f"目的地: {request.city} | 天数: {request.travel_days}")
        print(f"{'='*60}\n")

        await self._pre_init_services()

        yield {"type": "init", "message": "正在初始化服务...", "progress": 5}

        initial_state = self._build_discovery_state(request, user_id)

        DISCOVERY_NODE_INFO = {
            "web_search_attractions": {"message": "🔍 正在搜索景点攻略...", "progress": 10, "done_msg": "✅ 景点攻略搜索完成"},
            "search_weather": {"message": "🌤️ 正在查询天气...", "progress": 10, "done_msg": "✅ 天气查询完成"},
            "extract_attractions_expanded": {"message": "🧠 正在提取景点...", "progress": 30, "done_msg": "✅ 景点提取完成"},
            "geocode_dispatch": {"message": "📍 准备获取景点详情...", "progress": 35, "done_msg": "✅ 景点分批准备完成"},
            "geocode_batch": {"message": "📍 正在获取景点详情...", "progress": 70, "done_msg": "✅ 一批景点详情获取完成"},
            "gather_discovery": {"message": "🔗 汇总发现结果...", "progress": 90, "done_msg": "✅ 发现阶段完成"},
        }

        completed_nodes = set()
        final_state = dict(initial_state)

        try:
            async for chunk in self.discovery_app.astream(initial_state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if isinstance(node_output, dict):
                        for key, value in node_output.items():
                            if key in final_state:
                                existing = final_state[key]
                                if isinstance(existing, list) and isinstance(value, list):
                                    existing.extend(value)
                                else:
                                    final_state[key] = value
                            else:
                                final_state[key] = value

                        if "discovered_attractions" in node_output:
                            for attr in node_output["discovered_attractions"]:
                                yield {"type": "attraction", "data": attr}

                        if "weather_info" in node_output and node_output["weather_info"]:
                            yield {"type": "weather", "data": node_output["weather_info"]}

                    if node_name in DISCOVERY_NODE_INFO and node_name not in completed_nodes:
                        completed_nodes.add(node_name)
                        info = DISCOVERY_NODE_INFO[node_name]
                        yield {
                            "type": "progress",
                            "node": node_name,
                            "message": info["done_msg"],
                            "progress": info["progress"],
                        }

            total = len(final_state.get("discovered_attractions", []))
            yield {
                "type": "complete",
                "message": f"✅ 发现 {total} 个景点!",
                "progress": 100,
                "data": {"total": total},
            }

            print(f"{'='*60}")
            print(f"✅ 景点发现完成! 共 {total} 个景点")
            print(f"{'='*60}\n")

        except Exception as e:
            print(f"❌ 景点发现失败: {str(e)}")
            import traceback
            traceback.print_exc()
            yield {"type": "error", "message": f"发现失败: {str(e)}", "progress": 0}

    async def plan_from_selections_stream(self, request, selected_attractions,
                                           day_assignments=None, weather_info="",
                                           user_id="default"):
        """基于用户选择的景点进行流式规划 — yield SSE 事件"""
        print(f"\n{'='*60}")
        print(f"🚀 基于用户选择开始规划行程...")
        print(f"目的地: {request.city} | 选中景点: {len(selected_attractions)} 个")
        print(f"{'='*60}\n")

        await self._pre_init_services()

        yield {"type": "init", "message": "正在初始化服务...", "progress": 5}

        initial_state = self._build_planning_state(
            request, selected_attractions, day_assignments,
            weather_info, user_id
        )

        PLANNING_NODE_INFO = {
            "cluster_from_selections": {"message": "📊 正在聚类分析景点...", "progress": 15, "done_msg": "✅ 景点聚类完成"},
            "search_food": {"message": "🍜 正在搜索美食...", "progress": 30, "done_msg": "✅ 美食搜索完成"},
            "search_hotel": {"message": "🏨 正在搜索酒店...", "progress": 30, "done_msg": "✅ 酒店搜索完成"},
            "plan_route": {"message": "🗺️ 正在规划路线...", "progress": 40, "done_msg": "✅ 路线规划完成"},
            "macro_planner": {"message": "🏗️ 正在编排行程骨架...", "progress": 55, "done_msg": "✅ 行程骨架编排完成"},
            "day_plan_subgraph": {"message": "📝 正在生成每日行程...", "progress": 70, "done_msg": "✅ 每日行程生成完成"},
            "reduce_assemble": {"message": "🔧 正在合并行程数据...", "progress": 85, "done_msg": "✅ 行程合并完成"},
            "global_synthesizer": {"message": "💡 正在生成全局建议...", "progress": 90, "done_msg": "✅ 全局建议生成完成"},
            "extract_preferences": {"message": "📊 提取偏好...", "progress": 93, "done_msg": "✅ 偏好提取完成"},
            "save_preferences": {"message": "💾 保存偏好...", "progress": 95, "done_msg": "✅ 偏好保存完成"},
        }

        completed_nodes = set()
        final_state = dict(initial_state)

        try:
            async for chunk in self.planning_app.astream(initial_state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if isinstance(node_output, dict):
                        for key, value in node_output.items():
                            if key in final_state:
                                existing = final_state[key]
                                if isinstance(existing, list) and isinstance(value, list):
                                    existing.extend(value)
                                else:
                                    final_state[key] = value
                            else:
                                final_state[key] = value

                    if node_name in PLANNING_NODE_INFO and node_name not in completed_nodes:
                        completed_nodes.add(node_name)
                        info = PLANNING_NODE_INFO[node_name]
                        yield {
                            "type": "node_complete",
                            "node": node_name,
                            "message": info["done_msg"],
                            "progress": info["progress"],
                        }

            trip_plan = final_state.get("trip_plan")

            if not trip_plan:
                print("⚠️ 警告：生成的计划为空，使用备用方案")
                trip_plan = _create_fallback_plan(request, final_state)

            plan_dict = trip_plan.model_dump() if hasattr(trip_plan, 'model_dump') else trip_plan.dict()
            yield {"type": "complete", "message": "✅ 旅行计划生成完成!", "progress": 100, "data": plan_dict}

            print(f"{'='*60}")
            print(f"✅ 基于选择的行程规划完成!")
            print(f"{'='*60}\n")

        except Exception as e:
            print(f"❌ 行程规划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            yield {"type": "error", "message": f"规划失败: {str(e)}", "progress": 0}

    async def plan_trip(self, request, user_id: str = "default"):
        from ...models.schemas import TripRequest
        print(f"\n{'='*60}")
        print(f"🚀 开始 LangGraph 协作规划旅行...")
        print(f"目的地: {request.city} | 日期: {request.start_date} 至 {request.end_date}")
        print(f"{'='*60}\n")

        await self._pre_init_services()

        initial_state = self._build_initial_state(request, user_id)

        try:
            final_state = await self.app.ainvoke(initial_state)
            trip_plan = final_state.get("trip_plan")

            if not trip_plan:
                print("⚠️ 警告：生成的计划为空，可能大模型解析失败。将使用备用方案生成计划。")
                return _create_fallback_plan(request, final_state)

            print(f"{'='*60}")
            print(f"✅ LangGraph 旅行计划生成完成!")
            print(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return _create_fallback_plan(request)

    async def plan_trip_stream(self, request, user_id: str = "default"):
        from ...models.schemas import TripRequest
        print(f"\n{'='*60}")
        print(f"🚀 开始 LangGraph 流式协作规划旅行...")
        print(f"目的地: {request.city} | 日期: {request.start_date} 至 {request.end_date}")
        print(f"{'='*60}\n")

        await self._pre_init_services()

        yield {"type": "init", "message": "正在初始化服务...", "progress": 5}

        initial_state = self._build_initial_state(request, user_id)

        NODE_INFO = {
            "load_user_preferences": {"message": "📋 加载用户偏好...", "progress": 5, "done_msg": "✅ 用户偏好加载完成"},
            "web_search_attractions": {"message": "🔍 正在搜索景点攻略...", "progress": 8, "done_msg": "✅ 景点攻略搜索完成"},
            "extract_attractions": {"message": "🧠 正在提取核心景点...", "progress": 12, "done_msg": "✅ 核心景点提取完成"},
            "geocode_attractions": {"message": "📍 正在查询景点坐标...", "progress": 15, "done_msg": "✅ 景点坐标查询完成"},
            "search_weather": {"message": "🌤️ 正在查询天气...", "progress": 10, "done_msg": "✅ 天气查询完成"},
            "search_hotel": {"message": "🏨 正在推荐酒店...", "progress": 10, "done_msg": "✅ 酒店推荐完成"},
            "gather_search": {"message": "🔗 汇总搜索结果...", "progress": 15, "done_msg": "✅ 搜索结果汇总完成"},
            "error_handler": {"message": "🚨 处理错误...", "progress": 18, "done_msg": "⚠️ 错误已记录，继续处理"},
            "cluster_attractions": {"message": "📊 正在聚类分析景点...", "progress": 30, "done_msg": "✅ 景点聚类完成"},
            "search_food": {"message": "🍜 正在搜索美食...", "progress": 45, "done_msg": "✅ 美食搜索完成"},
            "plan_route": {"message": "🗺️ 正在规划路线...", "progress": 55, "done_msg": "✅ 路线规划完成"},
            "macro_planner": {"message": "🏗️ 正在宏观编排行程骨架...", "progress": 65, "done_msg": "✅ 行程骨架编排完成"},
            "day_plan_subgraph": {"message": "📝 正在并行生成每日行程...", "progress": 75, "done_msg": "✅ 每日行程生成完成"},
            "reduce_assemble": {"message": "🔧 正在合并行程数据...", "progress": 85, "done_msg": "✅ 行程合并完成"},
            "global_synthesizer": {"message": "💡 正在生成全局建议...", "progress": 90, "done_msg": "✅ 全局建议生成完成"},
            "extract_preferences": {"message": "📊 提取偏好...", "progress": 93, "done_msg": "✅ 偏好提取完成"},
            "save_preferences": {"message": "💾 保存偏好...", "progress": 95, "done_msg": "✅ 偏好保存完成"},
        }

        completed_nodes = set()
        executing_nodes = set()
        final_state = dict(initial_state)

        try:
            async for chunk in self.app.astream(initial_state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if isinstance(node_output, dict):
                        for key, value in node_output.items():
                            if key in final_state:
                                existing = final_state[key]
                                if isinstance(existing, list) and isinstance(value, list):
                                    existing.extend(value)
                                else:
                                    final_state[key] = value
                            else:
                                final_state[key] = value

                    if node_name in NODE_INFO and node_name not in completed_nodes and node_name not in executing_nodes:
                        executing_nodes.add(node_name)
                        info = NODE_INFO[node_name]
                        yield {
                            "type": "node_start",
                            "node": node_name,
                            "message": info["message"],
                            "progress": max(0, info["progress"] - 5),
                        }

                    if node_name in NODE_INFO and node_name not in completed_nodes:
                        completed_nodes.add(node_name)
                        executing_nodes.discard(node_name)
                        info = NODE_INFO[node_name]
                        yield {
                            "type": "node_complete",
                            "node": node_name,
                            "message": info["done_msg"],
                            "progress": info["progress"],
                        }

            trip_plan = final_state.get("trip_plan")

            if not trip_plan:
                print("⚠️ 警告：生成的计划为空，使用备用方案")
                trip_plan = _create_fallback_plan(request, final_state)

            plan_dict = trip_plan.model_dump() if hasattr(trip_plan, 'model_dump') else trip_plan.dict()
            yield {"type": "complete", "message": "✅ 旅行计划生成完成!", "progress": 100, "data": plan_dict}

            print(f"{'='*60}")
            print(f"✅ LangGraph 流式旅行计划生成完成!")
            print(f"{'='*60}\n")

        except Exception as e:
            print(f"❌ 流式生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            yield {"type": "error", "message": f"生成失败: {str(e)}", "progress": 0}


_langgraph_planner = None


def get_trip_planner_agent() -> LangGraphTripPlanner:
    global _langgraph_planner
    if _langgraph_planner is None:
        _langgraph_planner = LangGraphTripPlanner()
    return _langgraph_planner
