import { describe, expect, it } from 'vitest'
import { romanizeCity } from '@/components/loader/cityRomanization'

describe('romanizeCity', () => {
  it('命中映射表返回大写罗马名', () => {
    expect(romanizeCity('北京')).toBe('BEIJING')
    expect(romanizeCity('上海')).toBe('SHANGHAI')
    expect(romanizeCity('香港')).toBe('HONG KONG')
  })

  it('未命中的中文返回 null（避免重复出中文）', () => {
    expect(romanizeCity('景德镇')).toBeNull()
  })

  it('空串返回 null', () => {
    expect(romanizeCity('')).toBeNull()
  })

  it('纯拉丁字符城市名直接大写', () => {
    expect(romanizeCity('paris')).toBe('PARIS')
    expect(romanizeCity('Tokyo')).toBe('TOKYO')
  })
})
