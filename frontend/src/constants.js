// 全局常量：示例请求、SSE 超时、健康轮询间隔

// 与后端 backend/cli/main.py 的 EXAMPLE_REQUESTS 保持一致
export const EXAMPLE_REQUESTS = [
  '帮我策划一个500人的公司年会，预算20万，地点在北京朝阳，时间是下个月中旬',
  '策划一个200人的产品发布会，预算50万，上海浦东，需要高端场地',
  '组织一场100人的客户答谢会，预算10万，广州天河，注重用户体验',
  '安排一个300人的培训会，预算15万，深圳南山，需要完善的设备',
]

// 输入最大长度（与后端 PlanRequest 的 max_length=2000 一致）
export const INPUT_MAX_LENGTH = 2000

// SSE 无数据超时（ms）：需求提取 + 三个并行搜索 + 工具调用可能静默 30~60s 才吐字，
// 所以是"无数据超时"而非"总时长超时"，取 150s 安全。
export const SSE_TIMEOUT_MS = 150_000

// 健康状态轮询间隔（ms）
export const HEALTH_POLL_MS = 30_000
