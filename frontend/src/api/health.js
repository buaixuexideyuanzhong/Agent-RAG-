import { httpGet } from './http'

export function getHealth() {
  return httpGet('/health')
}
