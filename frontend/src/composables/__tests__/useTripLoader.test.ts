import { beforeEach, describe, expect, it } from 'vitest'
import { useTripLoader } from '@/composables/useTripLoader'

const ctx = { city: '北京', days: 5, attractionCount: 12 }

describe('useTripLoader 状态机', () => {
  beforeEach(() => {
    useTripLoader().reset()
  })

  it('初始为 idle，无 context', () => {
    const { state } = useTripLoader()
    expect(state.phase).toBe('idle')
    expect(state.context).toBeNull()
    expect(state.poster).toBeNull()
  })

  it('begin 进入 entering 并存下 poster/context', () => {
    const { begin, state } = useTripLoader()
    begin('construction', ctx)
    expect(state.phase).toBe('entering')
    expect(state.poster).toBe('construction')
    expect(state.context).toEqual(ctx)
  })

  it('setSteady 仅在 entering 时生效', () => {
    const loader = useTripLoader()
    loader.setSteady()
    expect(loader.state.phase).toBe('idle') // idle 时无效
    loader.begin('construction', ctx)
    loader.setSteady()
    expect(loader.state.phase).toBe('steady')
  })

  it('updateProgress 更新节点/消息/进度', () => {
    const loader = useTripLoader()
    loader.begin('construction', ctx)
    loader.updateProgress('macro_planner', '编排骨架', 62)
    expect(loader.state.currentNode).toBe('macro_planner')
    expect(loader.state.currentMessage).toBe('编排骨架')
    expect(loader.state.progress).toBe(62)
  })

  it('markReady 从 entering 或 steady 进入 flipping', () => {
    const loader = useTripLoader()
    loader.begin('construction', ctx)
    loader.setSteady()
    loader.markReady()
    expect(loader.state.phase).toBe('flipping')
  })

  it('markReady 在 idle 时无效', () => {
    const loader = useTripLoader()
    loader.markReady()
    expect(loader.state.phase).toBe('idle')
  })

  it('finishFlip 从 flipping 回 idle 并清空 context', () => {
    const loader = useTripLoader()
    loader.begin('construction', ctx)
    loader.markReady()
    loader.finishFlip()
    expect(loader.state.phase).toBe('idle')
    expect(loader.state.context).toBeNull()
  })

  it('dismiss 从任意活动态拉回 idle', () => {
    const loader = useTripLoader()
    loader.begin('construction', ctx)
    loader.setSteady()
    loader.dismiss()
    expect(loader.state.phase).toBe('idle')
    expect(loader.state.context).toBeNull()
  })
})
