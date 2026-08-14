// SSE 帧解析：把一帧（以 \n\n 分隔）里的所有 data: 行累加后 JSON.parse
// 非 JSON 帧 / 无 data 行返回 null（调用方忽略）
export function parseSseFrame(frame) {
  let data = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('data:')) data += line.slice(5).replace(/^ /, '')
  }
  if (!data) return null
  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}
