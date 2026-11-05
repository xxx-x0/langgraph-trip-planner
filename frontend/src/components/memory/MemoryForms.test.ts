import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import MemoryDateEditor from './MemoryDateEditor.vue'
import MemorySourcePicker from './MemorySourcePicker.vue'
import MemoryBackup from './MemoryBackup.vue'
import { unknownDate } from '@/utils/travelMemory'
const mocks = vi.hoisted(() => ({
  source: vi.fn(),
  sources: vi.fn(),
  previewRestore: vi.fn(),
  restore: vi.fn(),
}))
vi.mock('@/services/travelMemory', () => ({ memoryApi: mocks }))
beforeEach(() => {
  vi.clearAllMocks()
})
it('precision changes never fabricate missing date parts', async () => {
  const w = mount(MemoryDateEditor, {
    props: { modelValue: { precision: 'year', start: '2020', end: '' } },
  })
  await w.get('select').setValue('day')
  expect(w.emitted('update:modelValue')?.[0][0]).toEqual({
    precision: 'day',
    start: '',
    end: '',
  })
  await w.setProps({
    modelValue: { precision: 'day', start: '2020-05-06', end: '2020-05-08' },
  })
  await w.get('select').setValue('month')
  expect(w.emitted('update:modelValue')?.[1][0]).toEqual({
    precision: 'month',
    start: '2020-05',
    end: '2020-05',
  })
  w.unmount()
})
function sourceFixture() {
  return {
    kind: 'multi',
    id: 'mc_test',
    title: '苏杭旅行',
    basis: 'a'.repeat(64),
    visits: ['苏州', '杭州'].map((city, i) => ({
      id: String(i),
      city,
      region: '',
      country: '中国',
      latitude: 30,
      longitude: 120,
      when: unknownDate(),
      planned_start: '2020-05-01',
      planned_end: '2020-05-03',
    })),
  }
}
it('requires explicit actual cities and does not automatically reuse planned dates', async () => {
  mocks.source.mockResolvedValue(sourceFixture())
  const w = mount(MemorySourcePicker, {
    props: { initialKind: 'multi', initialId: 'mc_test' },
  })
  await flushPromises()
  expect(w.find('form').exists()).toBe(false)
  const confirm = w.get('.memory-source-confirm > button')
  expect(confirm.attributes()).toHaveProperty('disabled')
  expect(
    w
      .findAll('fieldset input')
      .every((i) => !(i.element as HTMLInputElement).checked),
  ).toBe(true)
  await w.findAll('fieldset input')[0].setValue(true)
  await confirm.trigger('click')
  const emitted = w.emitted('select')![0]
  expect((emitted[1] as any[]).map((v) => v.city)).toEqual(['苏州'])
  expect(emitted[2]).toEqual(unknownDate())
  w.unmount()
})
it('reuses dates only after separate confirmation and excludes future dates', async () => {
  mocks.source.mockResolvedValue(sourceFixture())
  const w = mount(MemorySourcePicker, {
    props: { initialKind: 'multi', initialId: 'mc_test' },
  })
  await flushPromises()
  await w.findAll('fieldset input')[1].setValue(true)
  await w.get('.memory-source-confirm > label input').setValue(true)
  await w.get('.memory-source-confirm > button').trigger('click')
  expect(w.emitted('select')![0][2]).toEqual({
    precision: 'day',
    start: '2020-05-01',
    end: '2020-05-03',
  })
  w.unmount()
  const future = sourceFixture()
  future.visits[0].planned_end = '2999-01-01'
  mocks.source.mockResolvedValue(future)
  const f = mount(MemorySourcePicker, {
    props: { initialKind: 'multi', initialId: 'mc_test' },
  })
  await flushPromises()
  await f.findAll('fieldset input')[0].setValue(true)
  expect(f.find('.memory-source-confirm > label input').exists()).toBe(false)
  f.unmount()
})
it('keeps a failed restore review visible and never reports success or reloads records', async () => {
  mocks.previewRestore.mockResolvedValue({
    token: 't',
    counts: { new: 1, conflict: 1, identical: 0, already_restored: 0 },
    items: [],
    photo_files_to_restore: 2,
  })
  mocks.restore.mockRejectedValue(new Error('预览后本机记录已改变'))
  const w = mount(MemoryBackup)
  const input = w.get('input[type=file]')
  Object.defineProperty(input.element, 'files', {
    value: [new File(['archive'], 'backup.zip')],
    configurable: true,
  })
  await input.trigger('change')
  await flushPromises()
  expect(w.text()).toContain('恢复前核对')
  await w.get('.memory-restore-preview .memory-primary').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('预览后本机记录已改变')
  expect(w.find('.memory-restore-preview').exists()).toBe(true)
  expect(w.emitted('restored')).toBeUndefined()
  w.unmount()
})
