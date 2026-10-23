import { afterEach, expect, it, vi } from 'vitest'
import { createDraftFromSelectionsStream } from './api'

afterEach(()=>{vi.unstubAllGlobals();sessionStorage.clear()})
it('reuses the creation request after a lost stream and clears it after completion',async()=>{
  const bodies: any[]=[]
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async(_url,init)=>{
    bodies.push(JSON.parse(init.body))
    const text=bodies.length===1 ? 'data: {"type":"node_complete","node":"save_draft"}\n\n' : 'data: {"type":"complete","draft_id":"saved"}\n\n'
    return new Response(text)
  }))
  const args: Parameters<typeof createDraftFromSelectionsStream>=[{city:'苏州',hotel_occupancy:{room_count:1,adults_per_room:2,children_ages:[8]}} as any,[{name:'A'}],[[{name:'A'}]],'weather',vi.fn()]
  await expect(createDraftFromSelectionsStream(...args)).rejects.toThrow('中断')
  await createDraftFromSelectionsStream(...args)
  expect(bodies[0].request_id).toBeTruthy()
  expect(bodies[1].request_id).toBe(bodies[0].request_id)
  expect(bodies[1].request.hotel_occupancy).toEqual({room_count:1,adults_per_room:2,children_ages:[8]})
  expect(bodies[1].selected_attractions).toEqual([{name:'A'}])
  expect(sessionStorage.getItem('pendingDraftCreation')).toBeNull()
})
