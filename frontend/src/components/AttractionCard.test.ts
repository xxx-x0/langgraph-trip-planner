import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AttractionCard from './AttractionCard.vue'

describe('AttractionCard', () => {
  it('uses attraction image_url when no photoUrl override is provided', () => {
    const wrapper = mount(AttractionCard, {
      props: {
        globalIndex: 1,
        attraction: {
          name: '平江路',
          address: '白塔东路65号',
          visit_duration: 120,
          description: '',
          image_url: 'http://store.is.autonavi.com/showpic/pingjiang',
        },
      },
    })

    expect(wrapper.find('img.attraction-image').attributes('src')).toBe(
      'http://store.is.autonavi.com/showpic/pingjiang'
    )
  })
})
