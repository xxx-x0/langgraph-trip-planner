from typing import Dict, Any

from ..state import TripPlannerState


async def plan_route_node(state: TripPlannerState) -> Dict[str, Any]:
    """路线规划已下沉到 day_plan_subgraph 中的 day_route_planner_node，此节点保留为空操作以维持图结构兼容。"""
    print("🗺️ 执行节点: plan_route_node (空操作，路线规划已移至单日子图)")
    return {"route_info": ""}
