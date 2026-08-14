// 数值与字段格式化工具

// 预算（元）→ 友好展示：≥1万显示 x.x万，否则显示 ¥x,xxx
export function formatBudget(v) {
  if (v == null || v === '') return ''
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  if (n >= 10000) {
    const w = n / 10000
    return `¥${w % 1 === 0 ? w : w.toFixed(1)}万`
  }
  return `¥${n.toLocaleString('zh-CN')}`
}

// 从 requirements 里提取入库 metadata（剔除 null/undefined/空串）
export function pickMeta(req) {
  const keys = ['activity_type', 'attendee_count', 'budget', 'city', 'theme']
  const meta = {}
  for (const k of keys) {
    const v = req?.[k]
    if (v != null && v !== '') meta[k] = v
  }
  return meta
}

// 截断展示 case id
export function clipId(id, n = 8) {
  return id ? (id.length > n ? `${id.slice(0, n)}…` : id) : ''
}
