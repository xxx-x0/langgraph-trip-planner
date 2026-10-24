/** Immediate form feedback; the server remains authoritative for itinerary constraints. */
export interface PlanInputIssue { field: string; message: string }
export function multiTripInputIssues(plan: any): PlanInputIssue[] {
  const issues: PlanInputIssue[] = []
  const add = (field: string, message: string) => issues.push({field, message})
  const date = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value || '') && Number.isFinite(Date.parse(value))
  if (!plan.title?.trim()) add('trip-title', '请给这趟旅行起一个名字。')
  if (!date(plan.start_date)) add('trip-start', '请选择旅行开始日期。')
  if (!date(plan.end_date)) add('trip-end', '请选择旅行结束日期。')
  if (date(plan.start_date) && date(plan.end_date)) {
    const days = (Date.parse(plan.end_date) - Date.parse(plan.start_date)) / 86400000 + 1
    if (days < 5 || days > 10) add('trip-end', '多城市旅行支持 5～10 天，请调整整趟日期。')
  }
  plan.stops.forEach((stop: any, i: number) => {
    const name = stop.city.name?.trim() || `第 ${i + 1} 站`
    if (!stop.city.name?.trim()) add(`city-name-${stop.id}`, `请填写第 ${i + 1} 站的城市名称。`)
    if (!date(stop.start_date)) add(`city-start-${stop.id}`, `请选择${name}的抵达日期。`)
    if (!date(stop.end_date)) add(`city-end-${stop.id}`, `请选择${name}的离开日期。`)
    if (!date(stop.start_date) || !date(stop.end_date)) return
    if (stop.end_date < stop.start_date) add(`city-end-${stop.id}`, `${name}的离开日期不能早于抵达日期。`)
    if (date(plan.start_date) && stop.start_date < plan.start_date) add(`city-start-${stop.id}`, `${name}抵达日期早于旅行开始，请调整到 ${plan.start_date} 或之后。`)
    if (date(plan.end_date) && stop.end_date > plan.end_date) add(`city-end-${stop.id}`, `${name}离开日期超出旅行范围，请调整到 ${plan.end_date} 或之前。`)
    const previous = plan.stops[i - 1]
    if (previous && date(previous.end_date) && previous.end_date > stop.start_date) add(`city-start-${stop.id}`, `${name}与上一站停留重叠；同日换城请让上一站离开日期与本城抵达日期一致。`)
  })
  return issues
}
