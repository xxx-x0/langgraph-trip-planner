export interface TicketScheduleContext {
  kind: 'draft' | 'multi'
  draft_id: string
  revision?: number
  from_stop?: string
  to_stop?: string
  request?: unknown
  days_detail?: unknown[]
}
