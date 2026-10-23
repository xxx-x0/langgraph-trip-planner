// 类型定义

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location?: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number | null
  open_hours?: string
  tel?: string
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner' | 'main' | 'snack' | 'dessert' | 'cafe' | 'late_night'
  category?: 'main' | 'snack' | 'dessert' | 'cafe' | 'late_night'
  name: string
  address?: string
  location?: Location
  description?: string
  cuisine?: string
  rating?: number
  avg_cost?: number
  distance?: string
  poi_id?: string
  source?: 'nearby' | 'popular'
  estimated_cost?: number
}

export interface Hotel {
  quote?: HotelQuote | null
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
  // AIGoHotel 新增字段
  star_rating?: number
  price?: number
  original_price?: number
  currency?: string
  hotel_amenities?: string[]
  room_amenities?: string[]
  description?: string
  image_url?: string
  detail_url?: string
  distance_in_meters?: number
  hotel_id?: number | string
}

export interface CompanionInfo {
  count: number
  type: string
}

export interface Budget {
  is_complete?: boolean
  unknown_cost_items?: string[]
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
  budget_limit?: number
  is_within_budget?: boolean | null
}

export interface RouteSegment {
  from_name: string
  to_name: string
  distance: string
  duration: string
  mode: string
  detail: string
}

export interface DayPlan {
  overnight_stay?: boolean
  description_source?: string | null
  pending_confirmations?: string[]
  timeline_schedule?: Array<{ kind: "attraction" | "meal" | "hotel" | "travel" | "wait" | "free_time"; ref_name: string; start_time: string; end_time: string; start_minutes: number; end_minutes: number; duration: number; cost?: number | null; detail?: string; mode?: string; distance?: string }>
  meal_warnings?: string[]
  meal_adjustments?: string[]
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
  route_segments: RouteSegment[]
  timeline_order?: TimelineOrderItem[]
  day_start_time?: string
  transport_mode?: string
}

export interface TimelineOrderItem {
  kind: 'attraction' | 'meal' | 'hotel'
  ref_name: string
  phase?: 'start' | 'end'
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number
  night_temp: number
  wind_direction: string
  wind_power: string
}

export interface TripPlan {
  narrative_source?: string | null
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
  companions?: CompanionInfo
  trip_tagline?: string
  weather_summary?: string
  title?: string
  transport_mode?: string
}

export interface TripFormData {
  hotel_occupancy?: HotelOccupancy
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  food_preference: string
  free_text_input: string
  default_day_start_time?: string
  budget?: number
  companions?: CompanionInfo
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}

export interface TripRecord {
  id: number
  title: string
  city: string
  start_date: string
  end_date: string
  travel_days: number
  status: 'completed' | 'favorite' | 'archived'
  budget_limit?: number
  total_cost: number
  companion_type?: string
  companion_count: number
  tags: string[]
  cover_image?: string
  created_at?: string
  updated_at?: string
  plan?: TripPlan
  request?: TripFormData
}

export interface TripListResponse {
  success: boolean
  data: TripRecord[]
  total: number
  page: number
  page_size: number
}

export interface UserPreference {
  user_id: string
  preferred_hotel_types: string[]
  preferred_cuisines: string[]
  preferred_transportation: string[]
  budget_range?: number[]
  preferred_attraction_categories: string[]
  preferred_visit_duration: number
  preferred_attractions_per_day: number
  preferred_meal_price_range: number[]
  preferred_hotel_price_range: number[]
  total_trips: number
  cities_visited: string[]
  last_updated: string
}

export interface DiscoveredAttraction {
  name: string
  description: string
  address: string
  category: string
  rating?: number
  ticket_price?: string
  image_url?: string
  open_hours?: string
  tel?: string
  location?: Location
  poi_id?: string
  selected?: boolean
  manuallyAdded?: boolean
  visit_minutes?: number
  recommendation?: 'must' | 'optional' | null
  recommendation_reason?: string
  recommendation_tags?: string[]
}

export interface DiscoveryStreamEvent {
  type: 'attraction' | 'weather' | 'hotels' | 'progress' | 'complete' | 'error'
  message?: string
  data?: any
  node?: string
  progress?: number
}

export interface PlanFromSelectionsPayload {
  request: TripFormData
  selected_attractions: DiscoveredAttraction[]
  day_assignments?: DiscoveredAttraction[][]
  weather_info: string
  user_id?: string
}

export interface DayDurationInfo {
  day_index: number
  total_minutes: number
  warning?: string | null
}

export interface PreviewDayAssignmentResponse {
  day_assignments: DiscoveredAttraction[][]
  day_durations: DayDurationInfo[]
}


export interface HotelOccupancy {
  room_count: number
  adults_per_room: number
  children_ages: number[]
}


export interface HotelQuote {
  source: string
  cost_kind: 'query_quote' | 'user_estimate' | 'system_estimate' | 'paid' | 'unknown'
  status: string
  amount?: number | null
  currency?: string | null
  unit: 'average_per_room_night' | 'total_stay' | 'unknown'
  check_in: string
  check_out: string
  nights: number
  occupancy: HotelOccupancy
  occupancy_confirmed: boolean
  queried_at: string
  unsupported_conditions: string[]
  room_name?: string | null
  bed_type?: string | null
  meal_plan?: string | null
  cancellation_policy?: string | null
  taxes_included?: boolean | null
  availability: string
}
