"""数据模型定义"""

from enum import Enum
from typing import Dict, List, Optional, Union, Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date
from .journey import Journey, local_instant
from .rest import RestPeriod, validate_rest_periods
from zoneinfo import ZoneInfo


# ============ 请求模型 ============

class CompanionInfo(BaseModel):
    """出行同伴信息"""
    count: int = Field(default=1, description="出行人数", ge=1, le=20, example=2)
    type: str = Field(default="solo", description="同伴类型: solo/couple/family/friends/elderly/group", example="couple")


class HotelOccupancy(BaseModel):
    """同一批房间具有相同入住配置；不同配置须分别查询。"""
    room_count: int = Field(default=1, ge=1, le=10)
    adults_per_room: int = Field(default=1, ge=1, le=20)
    children_ages: List[int] = Field(default_factory=list, max_length=10)

    @field_validator('children_ages')
    @classmethod
    def valid_ages(cls, ages):
        if any(age < 0 or age > 17 for age in ages):
            raise ValueError('儿童年龄须为0～17岁')
        return ages


class TripRequest(BaseModel):
    """旅行规划请求"""
    journey: Optional[Journey] = None
    rest_periods: List[RestPeriod] = Field(default_factory=list, max_length=60)
    city: str = Field(..., description="目的地城市", example="北京")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD", example="2025-06-01")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD", example="2025-06-03")
    travel_days: int = Field(..., description="旅行天数", ge=1, le=30, example=3)
    transportation: str = Field(..., description="交通方式", example="公共交通")
    accommodation: str = Field(..., description="住宿偏好", example="经济型酒店")
    preferences: List[str] = Field(default=[], description="旅行偏好标签", example=["历史文化", "美食"])
    meal_budget_per_person: Optional[int] = Field(default=None, ge=1, le=10000)
    dietary_requirements: str = Field(default="", max_length=300)
    dining_style: Literal["on_route", "dedicated"] = "on_route"
    food_preference: str = Field(default="本地特色", description="美食偏好", example="本地特色")
    free_text_input: Optional[str] = Field(default="", description="额外要求", example="希望多安排一些博物馆")
    budget: Optional[int] = Field(default=None, description="总预算上限(元)，为空表示不限预算", example=5000)
    companions: Optional[CompanionInfo] = Field(default=None, description="出行同伴信息")
    hotel_occupancy: Optional[HotelOccupancy] = None
    default_day_start_time: str = Field(
        default="08:00",
        description="每日行程默认开始时间 HH:mm，草稿中的单日设置可覆盖",
    )

    @model_validator(mode='after')
    def validate_hotel_occupancy(self):
        start, end = date.fromisoformat(self.start_date), date.fromisoformat(self.end_date)
        if end < start or (end-start).days >= 30:
            raise ValueError('行程日期须正序且不超过30天')
        validate_rest_periods(self.rest_periods, start, end)
        if self.journey:
            planning = self.journey.planning
            if planning:
                for direction, policy, boundary in [('outbound', planning.arrival_policy, planning.ready_at), ('inbound', planning.departure_policy, planning.leave_by)]:
                    if getattr(self.journey, direction) or policy != 'time_window':
                        continue
                    if not boundary:
                        raise ValueError('请选择班次未定时的目的地可用时间')
                    value = local_instant(boundary, self.journey.destination_timezone)
                    if not start <= value.date() <= end:
                        raise ValueError('预计目的地可用时间须在整趟出行日期范围内')
            for leg in (self.journey.outbound, self.journey.inbound):
                if not leg: continue
                if leg.passengers != (self.companions.count if self.companions else 1):
                    raise ValueError('交通人数须与同行人数一致')
                for value,zone in ((leg.departure_time,leg.departure_timezone),(leg.arrival_time,leg.arrival_timezone)):
                    if not start <= local_instant(value,zone).astimezone(ZoneInfo(self.journey.destination_timezone)).date() <= end:
                        raise ValueError('交通日期（按目的地时区）须在旅行日期范围内；跨日到达请扩大日期范围')
        if self.hotel_occupancy and self.companions:
            o = self.hotel_occupancy
            if o.room_count * (o.adults_per_room + len(o.children_ages)) != self.companions.count:
                raise ValueError('房间入住总人数须与出行人数一致；各间房按相同入住配置查询')
        return self

    @field_validator("travel_days", mode="before")
    @classmethod
    def validate_travel_days(cls, v, info):
        values = info.data
        start = values.get("start_date")
        end = values.get("end_date")
        if start and end:
            from datetime import datetime
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                end_dt = datetime.strptime(end, "%Y-%m-%d")
                expected_days = (end_dt - start_dt).days + 1
                if v != expected_days:
                    print(f"⚠️ travel_days校验: 传入{v}天，根据日期范围计算应为{expected_days}天，已自动修正")
                    return expected_days
            except Exception:
                pass
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "city": "北京",
                "start_date": "2025-06-01",
                "end_date": "2025-06-03",
                "travel_days": 3,
                "transportation": "公共交通",
                "accommodation": "经济型酒店",
                "preferences": ["历史文化", "美食"],
                "food_preference": "本地特色",
                "free_text_input": "希望多安排一些博物馆",
                "budget": 5000,
                "companions": {"count": 2, "type": "couple"}
            }
        }


class POISearchRequest(BaseModel):
    """POI搜索请求"""
    keywords: str = Field(..., description="搜索关键词", example="故宫")
    city: str = Field(..., description="城市", example="北京")
    citylimit: bool = Field(default=True, description="是否限制在城市范围内")


class GeoRequest(BaseModel):
    """地理编码请求"""
    address: str = Field(..., description="地址描述", example="北京市天安门")
    city: Optional[str] = Field(default=None, description="城市名称", example="北京")


class RouteRequest(BaseModel):
    """路线规划请求"""
    origin_address: str = Field(..., description="起点地址", example="北京市朝阳区阜通东大街6号")
    destination_address: str = Field(..., description="终点地址", example="北京市海淀区上地十街10号")
    origin_city: Optional[str] = Field(default=None, description="起点城市")
    destination_city: Optional[str] = Field(default=None, description="终点城市")
    route_type: str = Field(default="walking", description="路线类型: walking/driving/transit")


# ============ 响应模型 ============

class Location(BaseModel):
    """地理位置"""
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")


class Attraction(BaseModel):
    """景点信息"""
    name: str = Field(..., description="景点名称")
    address: str = Field(..., description="地址")
    location: Optional[Location] = Field(default=None, description="经纬度坐标")
    visit_duration: int = Field(..., description="建议游览时间(分钟)")
    description: str = Field(..., description="景点描述")
    category: Optional[str] = Field(default="景点", description="景点类别")
    rating: Optional[float] = Field(default=None, description="评分")
    photos: Optional[List[str]] = Field(default_factory=list, description="景点图片URL列表")
    poi_id: Optional[str] = Field(default="", description="POI ID")
    image_url: Optional[str] = Field(default=None, description="图片URL")
    ticket_price: Optional[int] = Field(default=None, ge=0, description="门票价格(元)，未知为null，明确免费为0")
    open_hours: Optional[str] = Field(default=None, description="开放时间")
    tel: Optional[str] = Field(default=None, description="联系电话")


class DiningCategory(str, Enum):
    """用餐类别（多类别候选池）"""
    MAIN = "main"           # 正餐
    SNACK = "snack"         # 小吃
    DESSERT = "dessert"     # 甜品
    CAFE = "cafe"           # 咖啡
    LATE_NIGHT = "late_night"  # 夜宵


class DiningCandidate(BaseModel):
    """候选池中的单个餐饮项"""
    name: str = Field(..., description="餐厅名称")
    address: Optional[str] = Field(default=None, description="地址")
    location: Optional[Location] = Field(default=None, description="坐标")
    category: DiningCategory = Field(..., description="餐饮类别")
    cuisine: Optional[str] = Field(default=None, description="菜系")
    rating: Optional[float] = Field(default=None, description="评分")
    avg_cost: Optional[int] = Field(default=None, description="人均消费")
    distance: Optional[str] = Field(default=None, description="距景点中心距离")
    open_hours: Optional[str] = Field(default=None, description="营业时间")
    tel: Optional[str] = Field(default=None, description="联系电话")
    poi_id: Optional[str] = Field(default=None, description="POI ID")
    source: str = Field(default="nearby", description="来源: nearby/popular/user_custom")

    recommendation: Dict[str, Any] = Field(default_factory=dict)


class DiningPoolDay(BaseModel):
    """每日多类别餐饮候选池"""
    main: List[DiningCandidate] = Field(default_factory=list)
    snack: List[DiningCandidate] = Field(default_factory=list)
    dessert: List[DiningCandidate] = Field(default_factory=list)
    cafe: List[DiningCandidate] = Field(default_factory=list)
    late_night: List[DiningCandidate] = Field(default_factory=list)


class Meal(BaseModel):
    """餐饮信息"""
    type: str = Field(..., description="餐饮类型: breakfast/lunch/dinner/snack")
    category: Optional[DiningCategory] = Field(
        default=None,
        description="餐饮类别（新版本主用此字段，type 保留向后兼容）"
    )
    name: str = Field(..., description="餐厅名称")
    address: Optional[str] = Field(default=None, description="餐厅地址")
    location: Optional[Location] = Field(default=None, description="经纬度坐标")
    description: Optional[str] = Field(default=None, description="推荐理由")
    cuisine: Optional[str] = Field(default=None, description="菜系: 川菜/粤菜/日料/本地菜等")
    rating: Optional[float] = Field(default=None, description="评分(1-5)")
    avg_cost: Optional[int] = Field(default=None, description="人均消费(元)")
    distance: Optional[str] = Field(default=None, description="距离景点/酒店的距离")
    poi_id: Optional[str] = Field(default=None, description="POI ID")
    source: Optional[str] = Field(default=None, description="来源: nearby=景点周边, popular=城市热门")
    estimated_cost: int = Field(default=0, description="预估费用(元)")
    open_hours: Optional[str] = Field(default=None, description="营业时间")
    tel: Optional[str] = Field(default=None, description="联系电话")
    schedule_mode: Literal["auto", "manual"] = Field(default="manual", description="默认推荐可随景点排序调整，明确选择保留插入位置")
    preferred_slot: Optional[Literal["breakfast", "lunch", "dinner"]] = Field(default=None)

    recommendation: Dict[str, Any] = Field(default_factory=dict)


class HotelQuote(BaseModel):
    source: str = 'aigohotel'
    cost_kind: Literal['query_quote', 'user_estimate', 'system_estimate', 'paid', 'unknown'] = 'unknown'
    status: Literal['search_only', 'detail_returned', 'unavailable', 'failed', 'legacy_unverified'] = 'search_only'
    amount: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    currency: Optional[str] = None
    unit: Literal['average_per_room_night', 'total_stay', 'unknown'] = 'unknown'
    check_in: str
    check_out: str
    nights: int = Field(ge=0)
    occupancy: HotelOccupancy
    occupancy_confirmed: bool = False
    queried_at: str
    unsupported_conditions: List[str] = Field(default_factory=list)
    room_name: Optional[str] = None
    rate_plan_id: Optional[str] = None
    bed_type: Optional[str] = None
    meal_plan: Optional[str] = None
    cancellation_policy: Optional[str] = None
    taxes_included: Optional[bool] = None
    availability: Literal['returned', 'on_request', 'unavailable', 'unknown'] = 'unknown'
    # Raw provider facts selected for audit; never let the LLM fill quote fields.
    provider_price_field: Optional[str] = None


class Hotel(BaseModel):
    """酒店信息"""
    name: str = Field(..., description="酒店名称")
    address: str = Field(default="", description="酒店地址")
    location: Optional[Location] = Field(default=None, description="酒店位置")
    price_range: str = Field(default="", description="价格范围")
    rating: str = Field(default="", description="评分")
    distance: str = Field(default="", description="距离景点距离")
    type: str = Field(default="", description="酒店类型")
    estimated_cost: float = Field(default=0, description="兼容旧记录的估算；新报价以quote为准")
    quote: Optional[HotelQuote] = None
    # === AIGoHotel 新增字段 ===
    star_rating: Optional[float] = Field(default=None, description="星级(0-5)")
    price: Optional[float] = Field(default=None, description="实际价格")
    original_price: Optional[float] = Field(default=None, description="原价")
    currency: str = Field(default="CNY", description="币种")
    hotel_amenities: List[str] = Field(default_factory=list, description="酒店设施列表")
    room_amenities: List[str] = Field(default_factory=list, description="房间设施列表")
    description: str = Field(default="", description="酒店详细描述")
    image_url: Optional[str] = Field(default=None, description="酒店主图URL")
    detail_url: Optional[str] = Field(default=None, description="酒店详情页链接")
    distance_in_meters: Optional[int] = Field(default=None, description="距中心点距离(米)")
    hotel_id: Optional[Union[int, str]] = Field(default=None, description="AIGoHotel 酒店标识")

    recommendation: Dict[str, Any] = Field(default_factory=dict)


class RouteSegment(BaseModel):
    """路线段信息"""
    from_name: str = Field(..., description="起点名称")
    to_name: str = Field(..., description="终点名称")
    distance: str = Field(default="", description="距离(如: 3.5公里)")
    duration: str = Field(default="", description="预计时间(如: 25分钟)")
    mode: str = Field(default="", description="交通方式(如: 地铁/公交/步行/驾车)")
    detail: str = Field(default="", description="路线详情(如: 乘坐地铁1号线天安门东→王府井，约3站)")
    is_estimated: bool = False


class FixedActivityTime(BaseModel):
    kind: Literal['attraction', 'meal'] = 'attraction'
    ref_name: str = Field(min_length=1, max_length=160)
    start_time: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')


class DayTimeConstraints(BaseModel):
    """Explicit clock constraints; ordering locks remain a separate concern."""
    allow_start_shift: bool = True
    earliest_start_time: Optional[str] = Field(default=None, pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    fixed_start_time: Optional[str] = Field(default=None, pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    appointments: List[FixedActivityTime] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def consistent_times(self):
        if not self.allow_start_shift and not self.fixed_start_time:
            raise ValueError('固定开始时间须填写时刻')
        if self.fixed_start_time and self.earliest_start_time and self.fixed_start_time < self.earliest_start_time:
            raise ValueError('固定开始时间早于最早出发下界')
        keys = [(x.kind, x.ref_name) for x in self.appointments]
        if len(keys) != len(set(keys)):
            raise ValueError('同一活动不可设置重复固定时刻')
        return self


class DayPlan(BaseModel):
    """单日行程"""
    locked_attraction_names: List[str] = Field(default_factory=list)
    removed_attraction_names: List[str] = Field(default_factory=list)
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_index: int = Field(..., description="第几天(从0开始)")
    description: str = Field(..., description="当日行程说明")
    description_source: Optional[str] = None
    transportation: str = Field(..., description="交通方式")
    accommodation: str = Field(..., description="住宿")
    hotel: Optional[Hotel] = Field(default=None, description="推荐酒店")
    attractions: List[Attraction] = Field(default=[], description="景点列表")
    meals: List[Meal] = Field(default=[], description="餐饮列表")
    route_segments: List[RouteSegment] = Field(default=[], description="路线段列表")
    timeline_order: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="单日结果时间轴顺序",
    )
    time_constraints: Optional[DayTimeConstraints] = None
    day_start_time: Optional[str] = Field(
        default=None,
        description="单日行程开始时间 HH:mm",
    )
    timeline_schedule: List[Dict[str, Any]] = Field(default_factory=list, description="按路线计算的活动开始/结束时间")
    meal_warnings: List[str] = Field(default_factory=list, description="缺餐或用餐时段需要确认")
    meal_adjustments: List[str] = Field(default_factory=list, description="本次编辑的用餐保留与调整说明")
    overnight_stay: bool = Field(default=True, description="当天是否计一晚住宿，离开日为false")

    trip_intent: Dict[str, Any] = Field(default_factory=dict)
    pending_confirmations: List[str] = Field(default_factory=list)
    schedule_suggestion: Dict[str, Any] = Field(default_factory=dict)
    route_comparison: Dict[str, Any] = Field(default_factory=dict)
    travel_window: Dict[str, Any] = Field(default_factory=dict)
    rest_periods: List[RestPeriod] = Field(default_factory=list)


class WeatherInfo(BaseModel):
    """天气信息"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_weather: str = Field(default="", description="白天天气")
    night_weather: str = Field(default="", description="夜间天气")
    day_temp: Union[int, str] = Field(default=0, description="白天温度")
    night_temp: Union[int, str] = Field(default=0, description="夜间温度")
    wind_direction: str = Field(default="", description="风向")
    wind_power: str = Field(default="", description="风力")

    @field_validator('day_temp', 'night_temp', mode='before')
    @classmethod
    def parse_temperature(cls, v):
        """解析温度,移除°C等单位"""
        if isinstance(v, str):
            # 移除°C, ℃等单位符号
            v = v.replace('°C', '').replace('℃', '').replace('°', '').strip()
            try:
                return int(v)
            except ValueError:
                return 0
        return v


class Budget(BaseModel):
    """预算信息"""
    total_attractions: int = Field(default=0, description="景点门票总费用")
    total_hotels: float = Field(default=0, description="酒店已知费用小计")
    total_meals: int = Field(default=0, description="餐饮总费用")
    total_intercity: float = Field(default=0)
    total_transportation: float = Field(default=0, description="交通总费用")
    total: float = Field(default=0, description="总费用")
    budget_limit: Optional[int] = Field(default=None, description="用户预算上限(元)")
    is_within_budget: Optional[bool] = Field(default=None, description="是否在预算范围内")
    unknown_cost_items: List[str] = Field(default_factory=list, description="尚未计入总额的未知费用")
    is_complete: bool = Field(default=True, description="费用项是否齐全；缺项时总额仅为已知预估小计")


class DaySkeleton(BaseModel):
    day_index: int = Field(..., description="第几天(从0开始)")
    date: str = Field(..., description="日期 YYYY-MM-DD")
    attraction_names: List[str] = Field(..., description="当日核心景点名称列表")
    hotel_name: str = Field(default="", description="入住酒店标识")


class MacroPlan(BaseModel):
    city: str = Field(..., description="城市")
    total_days: int = Field(..., description="总天数")
    days: List[DaySkeleton] = Field(..., description="每日骨架列表")
    transportation: str = Field(default="公共交通", description="交通方式")
    accommodation: str = Field(default="经济型酒店", description="住宿偏好")


class TripPlan(BaseModel):
    """旅行计划"""
    journey: Optional[Journey] = None
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    days: List[DayPlan] = Field(..., description="每日行程")
    weather_info: List[WeatherInfo] = Field(default=[], description="天气信息")
    overall_suggestions: str = Field(..., description="总体建议")
    budget: Optional[Budget] = Field(default=None, description="预算信息")
    companions: Optional[CompanionInfo] = Field(default=None, description="出行同伴信息")
    narrative_source: Optional[str] = None
    trip_tagline: str = Field(default="", description="行程标题")
    weather_summary: str = Field(default="", description="天气一句话摘要")


class TripPlanResponse(BaseModel):
    """旅行计划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[TripPlan] = Field(default=None, description="旅行计划数据")
    warnings: List[str] = Field(default=[], description="降级警告信息")
    is_fallback: bool = Field(default=False, description="是否为降级方案")
    errors: List[str] = Field(default=[], description="错误详情列表")


class POIInfo(BaseModel):
    """POI信息"""
    id: str = Field(..., description="POI ID")
    name: str = Field(..., description="名称")
    type: str = Field(..., description="类型")
    address: str = Field(..., description="地址")
    location: Location = Field(..., description="经纬度坐标")
    tel: Optional[str] = Field(default=None, description="电话")
    typecode: Optional[str] = Field(default=None, description="类型编码")
    photo: Optional[str] = Field(default=None, description="图片URL")
    cost: Optional[str] = Field(default=None, description="人均消费/价格")
    rating: Optional[str] = Field(default=None, description="评分")
    detail_info: Optional[Dict[str, Any]] = Field(default=None, description="详细信息(来自详情查询)")


class POISearchResponse(BaseModel):
    """POI搜索响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: List[POIInfo] = Field(default=[], description="POI列表")


class RouteInfo(BaseModel):
    """路线信息"""
    distance: float = Field(..., description="距离(米)")
    duration: int = Field(..., description="时间(秒)")
    route_type: str = Field(..., description="路线类型")
    description: str = Field(..., description="路线描述")


class POIDetailResponse(BaseModel):
    """POI详情响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[dict] = Field(default=None, description="POI详情数据")


class GeoResponse(BaseModel):
    """地理编码响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[dict] = Field(default=None, description="地理编码结果")


class RouteResponse(BaseModel):
    """路线规划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[RouteInfo] = Field(default=None, description="路线信息")


class WeatherResponse(BaseModel):
    """天气查询响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: List[WeatherInfo] = Field(default=[], description="天气信息")


class DiscoveredAttraction(BaseModel):
    """景点发现结果 — 用于发现阶段展示给用户选择"""
    name: str = Field(..., description="景点名称")
    description: str = Field(default="", description="景点简介")
    address: str = Field(default="", description="地址")
    category: str = Field(default="景点", description="类别: 自然风光/历史文化/购物/美食/亲子等")
    rating: Optional[float] = Field(default=None, description="评分")
    ticket_price: Optional[str] = Field(default=None, description="门票价格描述")
    image_url: Optional[str] = Field(default=None, description="图片URL")
    location: Optional[Location] = Field(default=None, description="经纬度坐标")
    poi_id: Optional[str] = Field(default=None, description="高德POI ID")
    visit_minutes: Optional[int] = Field(default=None, description="预估游玩时长(分钟)")
    open_hours: Optional[str] = Field(default=None, description="开放时间")
    tel: Optional[str] = Field(default=None, description="联系电话")


class ManualSearchRequest(BaseModel):
    """手动搜索景点请求"""
    keywords: str = Field(..., description="搜索关键词")
    city: str = Field(..., description="城市名称")


class PlanFromSelectionsRequest(BaseModel):
    request_id: Optional[str] = Field(default=None, min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9-]+$')
    """基于用户选择的景点进行规划的请求"""
    request: TripRequest = Field(..., description="旅行基本请求")
    selected_attractions: List[DiscoveredAttraction] = Field(..., description="用户选中的景点列表")
    day_assignments: Optional[List[List[DiscoveredAttraction]]] = Field(default=None, description="用户自定义的日程分配")
    weather_info: str = Field(default="", description="发现阶段获取的天气信息")
    user_id: str = Field(default="default", description="用户标识")


class UserPreference(BaseModel):
    """用户偏好模型"""
    user_id: str = Field(default="default", description="用户标识")
    preferred_hotel_types: List[str] = Field(default_factory=list, description="偏好酒店类型")
    preferred_cuisines: List[str] = Field(default_factory=list, description="偏好菜系")
    preferred_transportation: List[str] = Field(default_factory=list, description="偏好交通方式")
    budget_range: Optional[List[int]] = Field(default=None, description="预算范围[min,max]")
    preferred_attraction_categories: List[str] = Field(default_factory=list, description="偏好景点类型")
    preferred_visit_duration: int = Field(default=120, description="平均游览时长(分钟)")
    preferred_attractions_per_day: int = Field(default=3, description="每天偏好景点数")
    preferred_meal_price_range: List[int] = Field(default_factory=lambda: [50, 100], description="人均餐饮消费范围[min,max]")
    preferred_hotel_price_range: List[int] = Field(default_factory=lambda: [200, 500], description="酒店价格区间[min,max]")
    total_trips: int = Field(default=0, description="历史出行次数")
    cities_visited: List[str] = Field(default_factory=list, description="去过的城市")
    last_updated: str = Field(default="", description="最后更新时间")


class UserPreferenceResponse(BaseModel):
    """用户偏好响应"""
    success: bool = Field(default=True, description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[UserPreference] = Field(default=None, description="偏好数据")


class DraftDayContext(BaseModel):
    """骨架阶段每日上下文"""
    day_index: int = Field(..., description="第几天(从0开始)")
    date: str = Field(..., description="日期 YYYY-MM-DD")
    attraction_names: List[str] = Field(default_factory=list)
    attractions: List[Attraction] = Field(default_factory=list)
    hotel: Optional[Hotel] = Field(default=None)
    dining_pool: DiningPoolDay = Field(default_factory=DiningPoolDay)
    weather: Optional[WeatherInfo] = Field(default=None)
    day_start_time: Optional[str] = Field(default=None)
    overnight_stay: bool = Field(default=True)
    companion_count: int = Field(default=1, ge=1)

    trip_intent: Dict[str, Any] = Field(default_factory=dict)
    pending_confirmations: List[str] = Field(default_factory=list)
    schedule_suggestion: Dict[str, Any] = Field(default_factory=dict)
    travel_window: Dict[str, Any] = Field(default_factory=dict)
    rest_periods: List[RestPeriod] = Field(default_factory=list)


class DayDetail(BaseModel):
    """详细阶段产物（每日装配后的完整时间轴）"""
    day_index: int
    date: str
    description: str = Field(default="", description="依据当前已保存安排生成的说明")
    description_source: Optional[str] = None
    attractions: List[Attraction] = Field(default_factory=list)
    hotel: Optional[Hotel] = Field(default=None)
    meals: List[Meal] = Field(default_factory=list)
    route_segments: List[RouteSegment] = Field(default_factory=list)
    day_start_time: Optional[str] = Field(default=None)
    time_constraints: Optional[DayTimeConstraints] = None
    timeline_order: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="[{kind:'attraction|meal|hotel', ref_name:'...'}]"
    )
    day_budget: Optional[Budget] = Field(default=None, description="当日预算")
    locked_attraction_names: List[str] = Field(
        default_factory=list,
        description="用户锁定在当天当前位置的景点名；AI 重排不可移动这些景点",
    )
    removed_attraction_names: List[str] = Field(
        default_factory=list,
        description="用户从当天删除的景点名；后续重算和 AI 重排需排除",
    )
    is_assembled: bool = Field(default=False)
    timeline_schedule: List[Dict[str, Any]] = Field(default_factory=list)
    meal_warnings: List[str] = Field(default_factory=list)
    meal_adjustments: List[str] = Field(default_factory=list, description="本次编辑的用餐保留与调整说明")
    overnight_stay: bool = Field(default=True)
    companion_count: int = Field(default=1, ge=1)

    trip_intent: Dict[str, Any] = Field(default_factory=dict)
    pending_confirmations: List[str] = Field(default_factory=list)
    schedule_suggestion: Dict[str, Any] = Field(default_factory=dict)
    route_comparison: Dict[str, Any] = Field(default_factory=dict)
    travel_window: Dict[str, Any] = Field(default_factory=dict)
    rest_periods: List[RestPeriod] = Field(default_factory=list)


class TripDraftPayload(BaseModel):
    """草稿完整载荷（GET /draft/{id} 返回）"""
    draft_id: str
    status: str = Field(..., description="skeleton/assembling/finalized/expired")
    finalized_trip_id: Optional[int] = None
    request: TripRequest
    city: str
    macro_plan: MacroPlan
    days: List[DraftDayContext]
    days_detail: List[Optional[DayDetail]]
    unassigned_attractions: List[Dict[str, Any]] = Field(default_factory=list)
    weather_info: List[WeatherInfo] = Field(default_factory=list)
    created_at: str
    updated_at: str


class DayEditRequest(BaseModel):
    """所有用户编辑端点共享的请求模型"""
    time_constraints: Optional[DayTimeConstraints] = None
    attractions_order: Optional[List[str]] = Field(
        default=None,
        description="按用户拖拽后的景点名顺序；不传则保留当前 day_detail.attractions 顺序"
    )
    locked_attraction_names: Optional[List[str]] = Field(
        default=None,
        description="当前锁定的景点名完整状态；不传则保留当前 day_detail.locked_attraction_names",
    )
    removed_attraction_names: Optional[List[str]] = Field(
        default=None,
        description="当前从当天删除的景点名完整状态；不传则保留当前 day_detail.removed_attraction_names",
    )
    meals: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="用户当前勾选的餐饮（完整状态，不是 patch）"
                    "；不传则保留 day_detail.meals；传 [] 则清空"
    )
    day_start_time: Optional[str] = Field(
        default=None,
        description="单日行程开始时间 HH:mm；不传则沿用现有或全程默认值",
    )


class AIRearrangeRequest(BaseModel):
    """AI 重新安排请求"""
    hint: Optional[str] = Field(default=None, description="给 LLM 的额外提示")


class FinalizeResponse(BaseModel):
    """SSE 流的 complete 事件载荷"""
    type: str = Field(default="complete")
    trip_id: int
    trip_plan: TripPlan


# ============ 错误响应 ============

class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = Field(default=False, description="是否成功")
    message: str = Field(..., description="错误消息")
    error_code: Optional[str] = Field(default=None, description="错误代码")


class DayDurationInfo(BaseModel):
    """单日估算时长（用于智能分配预览）"""
    day_index: int = Field(..., description="第几天，从0开始")
    total_minutes: int = Field(..., description="当日所有景点估算游玩总时长(分钟)")
    warning: Optional[str] = Field(default=None, description="提示文案，如'当天偏紧'")


class PreviewDayAssignmentRequest(BaseModel):
    """智能日程分配预览请求"""
    selected_attractions: List[DiscoveredAttraction] = Field(..., description="用户选中的景点列表")
    travel_days: int = Field(..., ge=1, description="旅行天数")


class PreviewDayAssignmentResponse(BaseModel):
    """智能日程分配预览响应"""
    day_assignments: List[List[DiscoveredAttraction]] = Field(..., description="每天的景点分配（每个景点带 visit_minutes）")
    day_durations: List[DayDurationInfo] = Field(..., description="每天的估算时长")


class LoadMoreAttractionsRequest(BaseModel):
    """加载更多景点请求"""
    city: str = Field(..., min_length=1, description="目的地城市")
    exclude_names: List[str] = Field(default_factory=list, description="已展示的景点名，需排除")
    batch_size: int = Field(default=20, ge=1, le=50, description="单次返回数量")
    categories: Optional[List[str]] = Field(default=None, description="可选的规范类目过滤（与缓存层 category 字段对齐）")


class LoadMoreAttractionsResponse(BaseModel):
    """加载更多景点响应"""
    attractions: List[Dict[str, Any]] = Field(default_factory=list, description="新一批景点 (DiscoveredAttraction 结构的 dict)")


class AISelectRequest(BaseModel):
    """AI 从当前景点池选景请求"""
    destination: str = Field(..., min_length=1, description="目的地城市")
    days: int = Field(..., ge=1, le=30, description="行程天数")
    attractions: List[Dict[str, Any]] = Field(default_factory=list, description="当前景点池")
    preferences: Optional[Dict[str, Any]] = Field(default=None, description="可选偏好")


class AISelectResponse(BaseModel):
    """AI 从当前景点池选景响应"""
    must_ids: List[str] = Field(default_factory=list, description="必去景点的 poi_id 列表")
    optional_ids: List[str] = Field(default_factory=list, description="可选景点的 poi_id 列表")
    reasons: Dict[str, str] = Field(default_factory=dict, description="poi_id 到推荐理由的映射")
    tags: Dict[str, List[str]] = Field(default_factory=dict, description="poi_id 到推荐标签列表的映射")
    summary: Optional[str] = Field(default=None, description="本次 AI 选景的总体说明")
