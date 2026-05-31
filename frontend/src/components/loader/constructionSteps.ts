// CONSTRUCTION（Discover→Draft 骨架）阶段的节点顺序与中文标签。
//
// ⚠️ 重要：这里的 key 必须与后端 create_planning_graph() 实际发出 node_complete
// 的节点一致，而不是主行程图(create_trip_planner_graph)的节点。
// 经核对 backend graph.py 的 plan_from_selections_stream / PLANNING_NODE_INFO，
// draft 流程真正会触发 node_complete 的只有：
//   cluster_from_selections / search_hotels_by_day / macro_planner
// 其余 search_dining_pool / save_draft / load_user_preferences 在图中但不发事件。
// 这里把用户可感知的步骤都列上，作为状态条标签来源；进度优先用后端事件自带的 progress，
// progressForNode 仅作兜底。
export interface ConstructionStep {
  key: string
  label: string
}

export const CONSTRUCTION_STEPS: ConstructionStep[] = [
  { key: 'cluster_from_selections', label: '聚类分析景点' },
  { key: 'search_dining_pool', label: '搜索美食' },
  { key: 'search_hotels_by_day', label: '搜索酒店' },
  { key: 'macro_planner', label: '编排行程骨架' },
  { key: 'save_draft', label: '生成行程草稿' },
]

export const CONSTRUCTION_TOTAL = CONSTRUCTION_STEPS.length

// 后端图中存在但不发 node_complete 的节点，仍给出标签以防偶发透传
const EXTRA_LABELS: Record<string, string> = {
  load_user_preferences: '加载偏好',
}

/** 给定当前节点 key，返回其中文标签；未知节点返回兜底文案。 */
export function labelForNode(nodeKey: string): string {
  return (
    CONSTRUCTION_STEPS.find((s) => s.key === nodeKey)?.label ??
    EXTRA_LABELS[nodeKey] ??
    '规划中'
  )
}

/** 给定当前节点 key，按其在序列中的序号算完成百分比（0-100，取整）。
 *  仅作兜底——优先使用后端事件自带的 progress。 */
export function progressForNode(nodeKey: string): number {
  const idx = CONSTRUCTION_STEPS.findIndex((s) => s.key === nodeKey)
  if (idx < 0) return 0
  return Math.round(((idx + 1) / CONSTRUCTION_TOTAL) * 100)
}
