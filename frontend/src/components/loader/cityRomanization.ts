/** 城市中文名 → 罗马名（大写）。未命中返回 null，调用方据此省略英文副标题。 */
const MAP: Record<string, string> = {
  北京: 'BEIJING', 上海: 'SHANGHAI', 广州: 'GUANGZHOU', 深圳: 'SHENZHEN',
  成都: 'CHENGDU', 杭州: 'HANGZHOU', 西安: 'XIAN', 重庆: 'CHONGQING',
  南京: 'NANJING', 苏州: 'SUZHOU', 厦门: 'XIAMEN', 三亚: 'SANYA',
  丽江: 'LIJIANG', 桂林: 'GUILIN', 青岛: 'QINGDAO', 武汉: 'WUHAN',
  长沙: 'CHANGSHA', 昆明: 'KUNMING', 大理: 'DALI', 香港: 'HONG KONG',
  // …可按实际服务城市增补
}

export function romanizeCity(city: string): string | null {
  if (!city) return null
  return MAP[city] ?? (/^[\x00-\x7F]+$/.test(city) ? city.toUpperCase() : null)
}
