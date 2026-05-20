"""草稿写入节点（骨架图的最后一站）"""
from typing import Dict, Any, List

from ..state import TripPlannerState
from ....services import trip_draft_service
from ....models.schemas import WeatherInfo


async def save_draft_node(state: TripPlannerState) -> Dict[str, Any]:
    print("💾 执行节点: save_draft_node")
    request = state["request"]
    user_id = state.get("user_id", "default")
    macro_plan = state.get("macro_plan")
    if macro_plan is None:
        raise RuntimeError("save_draft_node: macro_plan 缺失，无法保存草稿")

    # 把 weather_info（可能是字符串/列表）规范化为 List[WeatherInfo] dict
    weather_info_raw = state.get("weather_info", "")
    weather_list: List[Dict[str, Any]] = []
    if isinstance(weather_info_raw, list):
        for w in weather_info_raw:
            if isinstance(w, WeatherInfo):
                weather_list.append(w.model_dump(mode="json"))
            elif isinstance(w, dict):
                weather_list.append(w)

    draft_id = await trip_draft_service.create_draft(
        user_id=user_id,
        request=request,
        selected_attractions=state.get("user_selected_attractions", []) or [],
        macro_plan=macro_plan,
        clusters_data=state.get("clusters_data", []) or [],
        hotels_by_day=state.get("hotels_by_day", []) or [],
        dining_pool=state.get("dining_pool", []) or [],
        weather_info=weather_list,
    )
    print(f"✅ 草稿已保存: draft_id={draft_id}")
    return {"draft_id": draft_id}
