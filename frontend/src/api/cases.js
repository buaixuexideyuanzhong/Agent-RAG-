import { httpPost } from './http'

export function saveCase({ plan_text, metadata }) {
  return httpPost('/cases', { plan_text, metadata: metadata || {} })
}
