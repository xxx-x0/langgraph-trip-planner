"""单日叙述文案（独立 LLM 调用，不参与时间轴编排）"""
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

from ....models.schemas import DayDetail, WeatherInfo
from ....services.llm_service import get_llm
from ..exceptions import _invoke_llm_with_retry


_DAY_NARRATIVE_PROMPT = """你是旅行文案专家。请根据已确定的当日行程，写一段简短的当日叙述文案。

**严格约束:**
1. 不要重新编排顺序、不要推荐新景点/餐厅、不要生成时间轴
2. 仅输出 2-3 段 Markdown 文案（含穿衣建议、亮点、注意事项）
3. 字数 200-400 字之间
4. 不要列出门票价格、不要列出路线段距离时间
"""


async def write_day_narrative_llm(
    day_detail: DayDetail,
    weather: Optional[WeatherInfo] = None,
    free_text_input: Optional[str] = None,
    city: str = "",
) -> str:
    attrs = "、".join(a.name for a in day_detail.attractions)
    meals = "、".join(f"{m.name}({(m.category or m.type)})" for m in day_detail.meals)
    hotel_name = day_detail.hotel.name if day_detail.hotel else "未定"

    weather_line = ""
    if weather:
        weather_line = (
            f"天气: 白天{weather.day_weather} {weather.day_temp}°C / "
            f"夜间{weather.night_weather} {weather.night_temp}°C, "
            f"{weather.wind_direction} {weather.wind_power}"
        )

    free_text_line = ""
    if free_text_input:
        free_text_line = f"\n用户额外要求: {free_text_input}"

    prompt = f"""请为 {city} 的第 {day_detail.day_index + 1} 天 ({day_detail.date}) 写一段叙述文案。

已确定的安排:
- 景点: {attrs or '无'}
- 餐饮: {meals or '无（用户未选择）'}
- 入住: {hotel_name}
{weather_line}{free_text_line}

请按要求输出 Markdown 文案。"""

    llm = get_llm()
    try:
        response = await _invoke_llm_with_retry(
            llm, [SystemMessage(content=_DAY_NARRATIVE_PROMPT),
                  HumanMessage(content=prompt)]
        )
        text = (response.content or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return text
    except Exception as e:
        print(f"⚠️ write_day_narrative_llm 失败: {e}")
        return ""
