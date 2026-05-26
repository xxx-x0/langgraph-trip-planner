/**
 * 移除酒店名中末尾的括号英文部分。
 * 例："维景大酒店(Winjing Hotel)" → "维景大酒店"
 *
 * 同时处理半角和全角括号。
 */
export function cleanHotelName(name: string | undefined | null): string {
  if (!name) return ''
  return name.replace(/[(（][^)）]*[)）]/g, '').trim()
}
