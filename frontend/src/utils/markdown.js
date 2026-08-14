// markdown 渲染：marked + 中文序号标题预处理 + DOMPurify 消毒（LLM 输出纵深防御）
import { marked } from 'marked'
import createDOMPurify from 'dompurify'

// 浏览器中默认导出即带 .sanitize 的实例；Node（无 window，如单元测试）默认导出是工厂函数。
// 检测兜底：只有非浏览器环境才走空实现，真实浏览器永远走 DOMPurify 消毒。
const DOMPurify = typeof createDOMPurify.sanitize === 'function'
  ? createDOMPurify
  : { sanitize: (html) => html }

marked.setOptions({ gfm: true, breaks: true })

// GLM 输出的章节标题常为"一、活动概述"（无 # 前缀），进 marked 前把这类整行转成二级标题。
// 负向前瞻排除已带 # / | / > / - / * / ` 的行，避免误伤表格、列表、引用、代码。
const CN_HEADING = /^(?!\s*[#|>\-*`])\s*([一二三四五六七八九十]{1,4}、.*)$/gm

function preprocess(md) {
  return md.replace(CN_HEADING, '## $1')
}

export function renderPlan(md) {
  const html = marked.parse(preprocess(md || ''))
  return DOMPurify.sanitize(html)
}
