import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// 渲染测试不触发 GSAP 入场/收束；mock 插件避免 happy-dom 下的副作用。
vi.mock('gsap/Flip', () => ({ Flip: { fit: () => {} } }))
vi.mock('gsap/SplitText', () => ({ SplitText: { create: () => ({ chars: [], revert() {} }) } }))

import BauhausLoader from '@/components/loader/BauhausLoader.vue'
import { useTripLoader } from '@/composables/useTripLoader'

function ctx(over: Record<string, unknown> = {}) {
  return { city: '北京', days: 5, attractionCount: 12, metaLine: '2026-06-10 – 2026-06-14', ...over }
}

describe('BauhausLoader · REFINEMENT', () => {
  beforeEach(() => useTripLoader().reset())

  it('idle 时不渲染海报', () => {
    const w = mount(BauhausLoader)
    expect(w.find('.bh-loader').exists()).toBe(false)
    w.unmount()
  })

  it('refinement begin 后渲染四区，且不渲染 construction 海报', async () => {
    useTripLoader().begin('refinement', ctx())
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.find('.bh-poster--refine').exists()).toBe(true)
    expect(w.find('.pb-banner').exists()).toBe(true)
    expect(w.find('.pb-ledger').exists()).toBe(true)
    expect(w.find('.pb-spread').exists()).toBe(true)
    expect(w.find('.pb-status').exists()).toBe(true)
    expect(w.find('.bh-hero').exists()).toBe(false)
    w.unmount()
  })

  it('台账按真实天数渲染（N=3，无折叠）', async () => {
    useTripLoader().begin('refinement', ctx({ days: 3 }))
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.findAll('.pb-dayrow')).toHaveLength(3)
    expect(w.find('.pb-dayrow--fold').exists()).toBe(false)
    w.unmount()
  })

  it('N=7 渲染 7 行无折叠', async () => {
    useTripLoader().begin('refinement', ctx({ days: 7 }))
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.findAll('.pb-dayrow')).toHaveLength(7)
    expect(w.find('.pb-dayrow--fold').exists()).toBe(false)
    w.unmount()
  })

  it('N=12 渲染前 8 行 + 折叠行 +4', async () => {
    useTripLoader().begin('refinement', ctx({ days: 12 }))
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.findAll('.pb-dayrow')).toHaveLength(9) // 8 行 + 1 折叠行
    const fold = w.find('.pb-dayrow--fold')
    expect(fold.exists()).toBe(true)
    expect(fold.text()).toContain('+4')
    w.unmount()
  })

  it('状态条随 currentMessage 变化；缺省回退 定稿中…', async () => {
    useTripLoader().begin('refinement', ctx())
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.find('.pb-status-lbl').text()).toContain('定稿中')
    useTripLoader().updateProgress('synthesizer', '生成总体建议…', 0)
    await w.vm.$nextTick()
    expect(w.find('.pb-status-lbl').text()).toContain('生成总体建议')
    w.unmount()
  })

  it('城市命中映射显示英文副标题；未命中省略', async () => {
    useTripLoader().begin('refinement', ctx({ city: '北京' }))
    const w = mount(BauhausLoader)
    await w.vm.$nextTick()
    expect(w.find('.pb-banner-en').exists()).toBe(true)
    expect(w.find('.pb-banner-en').text()).toContain('BEIJING')
    w.unmount()

    useTripLoader().reset()
    useTripLoader().begin('refinement', ctx({ city: '景德镇' }))
    const w2 = mount(BauhausLoader)
    await w2.vm.$nextTick()
    expect(w2.find('.pb-banner-en').exists()).toBe(false)
    w2.unmount()
  })
})
