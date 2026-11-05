import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent } from 'vue'
import Editor from './TravelMemoryEditorView.vue'
import {
  emptyMemoryForm,
  formFromRecord,
  unknownDate,
} from '@/utils/travelMemory'
import { MemoryApiError } from '@/services/travelMemory'
import type { MemoryDraft, TravelMemory } from '@/types/travelMemory'
const state = vi.hoisted(() => ({
  draft: undefined as MemoryDraft | undefined,
  get: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  upload: vi.fn(),
  put: vi.fn(),
  remove: vi.fn(),
}))
vi.mock('@/services/memoryDrafts', () => ({
  memoryDrafts: {
    get: async () => state.draft,
    put: (...args: unknown[]) => state.put(...args),
    remove: (...args: unknown[]) => state.remove(...args),
  },
}))
vi.mock('@/services/travelMemory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/travelMemory')>()),
  memoryApi: state,
}))
const id = 'a'.repeat(32)
function saved(revision = 1): TravelMemory {
  return {
    id,
    revision,
    created_at: '',
    updated_at: '',
    document: {
      ...emptyMemoryForm(),
      title: '上次保存',
      source: null,
      deleted: false,
      photos: [],
      visits: [
        {
          id: 'v',
          city: '杭州',
          country: '中国',
          region: '浙江',
          latitude: 30,
          longitude: 120,
          when: unknownDate(),
        },
      ],
    },
  }
}
function draft(record = saved()): MemoryDraft {
  return {
    key: 'memory:' + id,
    id,
    serverId: id,
    revision: record.revision,
    form: formFromRecord(record),
    source: null,
    operationId: 'b'.repeat(32),
    pending: [],
    updated: 1,
    cachedRecord: record,
  }
}
let wrapper: ReturnType<typeof mount> | undefined
beforeEach(() => {
  vi.clearAllMocks()
  state.draft = undefined
  state.put.mockResolvedValue(undefined)
  state.remove.mockResolvedValue(undefined)
  vi.stubGlobal(
    'confirm',
    vi.fn(() => true),
  )
})
afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})
async function open(path = '/travel-records/' + id + '/edit') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/travel-records/:id/edit', component: Editor },
      {
        path: '/travel-records/:id',
        component: { template: '<div>Saved detail</div>' },
      },
      {
        path: '/travel-records',
        component: { template: '<div>Library</div>' },
      },
    ],
  })
  await router.push(path)
  await router.isReady()
  wrapper = mount(
    defineComponent({ components: { RouterView }, template: '<RouterView />' }),
    {
      global: {
        plugins: [router],
        stubs: { MemoryCityPicker: true, MemorySourcePicker: true },
      },
    },
  )
  await flushPromises()
  return { w: wrapper, router }
}
it('failed save retains editable text and a durable local draft without changing saved data', async () => {
  const record = saved()
  state.get.mockResolvedValue(record)
  state.update.mockRejectedValue(new MemoryApiError('服务暂不可用', 503))
  const { w, router } = await open()
  await w.get('textarea[maxlength="20000"]').setValue('未保存的新回忆')
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(w.text()).toContain('服务暂不可用')
  expect(
    (w.get('textarea[maxlength="20000"]').element as HTMLTextAreaElement).value,
  ).toBe('未保存的新回忆')
  expect(
    state.put.mock.calls[state.put.mock.calls.length - 1]?.[0].form.note,
  ).toBe('未保存的新回忆')
  expect(record.document.note).toBe('')
  expect(router.currentRoute.value.path).toContain('/edit')
})
it('stale local draft requires review and never overwrites automatically', async () => {
  state.draft = draft()
  state.draft.form.note = '本机版本'
  const latest = saved(2)
  latest.document.note = '其他页面的版本'
  state.get.mockResolvedValue(latest)
  state.update.mockImplementation(async (_id, rev, form) => ({
    ...latest,
    revision: rev + 1,
    document: { ...latest.document, ...form },
  }))
  const { w, router } = await open()
  expect(w.text()).toContain('已保存内容发生了变化')
  expect(w.get('button[type=submit]').attributes()).toHaveProperty('disabled')
  await w.get('.memory-conflict button').trigger('click')
  await flushPromises()
  expect(state.update).not.toHaveBeenCalled()
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(state.update.mock.calls[0][1]).toBe(2)
  expect(state.update.mock.calls[0][2].note).toBe('本机版本')
  expect(router.currentRoute.value.path).toBe('/travel-records/' + id)
})
it('failed initial read offers retry and cannot submit an empty replacement', async () => {
  state.get
    .mockRejectedValueOnce(new MemoryApiError('暂时无法连接服务', 0))
    .mockResolvedValueOnce(saved())
  const { w } = await open()
  expect(w.get('button[type=submit]').attributes()).toHaveProperty('disabled')
  await w.get('.memory-error button').trigger('click')
  await flushPromises()
  expect(
    (w.get('input[maxlength="160"]').element as HTMLInputElement).value,
  ).toBe('上次保存')
  expect(state.update).not.toHaveBeenCalled()
})
it('visiting an unchanged editor does not create a misleading unfinished draft', async () => {
  state.get.mockResolvedValue(saved())
  const { router } = await open()
  await router.push('/travel-records')
  await flushPromises()
  expect(state.put).not.toHaveBeenCalled()
})

it('restoring a memory fragment also restores its existing photo association', async () => {
  const record = saved()
  record.document.moments = [
    {
      id: 'moment',
      title: '片段',
      text: '记忆',
      place: '',
      visit_id: null,
      when: unknownDate(),
      deleted: false,
    },
  ]
  record.document.photos = [
    {
      id: 'c'.repeat(32),
      caption: '照片',
      moment_id: 'moment',
      deleted: false,
      focal_x: 50,
      focal_y: 50,
      sha256: 'd'.repeat(64),
      filename: 'image.jpg',
      media_type: 'image/jpeg',
      size: 100,
      width: 20,
      height: 10,
    },
  ]
  state.get.mockResolvedValue(record)
  const { w } = await open()
  const trash = w
    .findAll('button')
    .find((button) => button.text() === '移入片段回收站（保留照片）')!
  await trash.trigger('click')
  await flushPromises()
  expect(
    state.put.mock.calls[state.put.mock.calls.length - 1]?.[0].form.photos[0]
      .moment_id,
  ).toBe('moment')
  expect(w.text()).toContain('已移入回收站的片段（恢复后可见）')
  await w
    .findAll('button')
    .find((button) => button.text() === '恢复片段')!
    .trigger('click')
  await flushPromises()
  const local = state.put.mock.calls[state.put.mock.calls.length - 1]?.[0]
  expect(local.form.photos[0].moment_id).toBe('moment')
  expect(local.form.moments[0].deleted).toBe(false)
})
