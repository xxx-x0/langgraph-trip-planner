import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SelectableAttractionCard from './SelectableAttractionCard.vue'

describe('SelectableAttractionCard', () => {
  it('does not emit toggle while disabled', async () => {
    const wrapper = mount(SelectableAttractionCard, {
      props: {
        disabled: true,
        attraction: {
          name: '故宫博物院',
          address: '景山前街4号',
          description: '',
          category: '历史文化',
          selected: false,
        },
      },
    })

    await wrapper.trigger('click')

    expect(wrapper.emitted('toggle')).toBeUndefined()
    expect(wrapper.classes()).toContain('disabled')
    expect(wrapper.attributes('aria-disabled')).toBe('true')
  })

  it('shows AI recommendation reason and tags', () => {
    const wrapper = mount(SelectableAttractionCard, {
      props: {
        attraction: {
          name: '故宫博物院',
          address: '景山前街4号',
          description: '明清皇家宫殿',
          category: '历史文化',
          selected: true,
          recommendation: 'must',
          recommendation_reason: '符合你的历史文化偏好',
          recommendation_tags: ['历史文化', '经典必去'],
        },
      },
    })

    expect(wrapper.text()).toContain('符合你的历史文化偏好')
    expect(wrapper.text()).toContain('历史文化')
    expect(wrapper.text()).toContain('经典必去')
  })
})
