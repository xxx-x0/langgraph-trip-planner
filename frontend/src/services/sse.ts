export interface SSEOptions {
  timeout?: number
  signal?: AbortSignal
}

// The deadline covers headers AND the body. EOF without a terminal event is failure.
export async function postSSE<T extends { type: string; node?: string; step?: string; message?: string }>(
  url: string, body: unknown, onEvent: (event: T) => void,
  options: SSEOptions = {}, defaultTimeout = 180000,
): Promise<void> {
  const controller = new AbortController()
  const signal = options.signal ? AbortSignal.any([options.signal, controller.signal]) : controller.signal
  const timeoutId = setTimeout(() => controller.abort(), options.timeout ?? defaultTimeout)
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  let stage = '连接服务'
  let onAbort: () => void = () => {}
  const aborted = new Promise<never>((_, reject) => {
    onAbort = () => reject(new Error(`请求已取消或超时（${stage}），请重试；已保存草稿仍保留。`))
    signal.addEventListener('abort', onAbort, { once: true })
  })
  // Attach a handler before fetch, so cancellation during connection is handled.
  void aborted.catch(() => {})
  try {
    if (signal.aborted) throw new Error('请求已取消')
    const response = await Promise.race([fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal,
    }), aborted])
    if (!response.ok) throw new Error(`请求失败: ${response.status}（${stage}），请重试`)
    reader = response.body?.getReader()
    if (!reader) throw new Error('无法获取响应流，请重试')
    const decoder = new TextDecoder()
    let buffer = ''
    const dispatch = (frame: string): boolean => {
      const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
      if (!data) return false
      let event: T
      try { event = JSON.parse(data) as T }
      catch { throw new Error(`响应数据无法解析（${stage}），请重试`) }
      const key = event.step || event.node
      if (key) stage = ({ preparing:'整理行程', synthesizer:'生成总体建议', saving:'保存行程',
        macro_planner:'按日编排', search_weather:'查询天气', search_hotels_by_day:'查询酒店',
        search_dining_pool:'查询餐厅', save_draft:'保存草稿' } as Record<string,string>)[key] || event.message || '获取行程数据'
      onEvent(event) // Callback errors must propagate, never be mistaken for parse errors.
      return event.type === 'complete' || event.type === 'error'
    }
    while (true) {
      const { done, value } = await Promise.race([reader.read(), aborted])
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')
      let split: number
      while ((split = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, split)
        buffer = buffer.slice(split + 2)
        if (dispatch(frame)) return
      }
      if (done) {
        if (buffer.trim() && dispatch(buffer)) return
        throw new Error(`响应流在完成前中断（${stage}），请重试；当前选择和已保存草稿仍保留。`)
      }
    }
  } catch (error) {
    if (error instanceof TypeError) throw new Error(`连接中断（${stage}），请重试；已保存草稿仍保留。`)
    throw error
  } finally {
    clearTimeout(timeoutId)
    signal.removeEventListener('abort', onAbort)
    reader?.cancel().catch(() => {})
  }
}
