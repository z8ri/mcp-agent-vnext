import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'

// 只注册用得到的几种语言，不拉全量 highlight.js 语言包——
// 修的是参考代码"无语法高亮器"这个具体缺口，不是要做一个通用代码渲染器。
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('json', json)
hljs.registerLanguage('bash', bash)

const md = new MarkdownIt({
  html: false, // 和参考代码一样禁用原始 HTML，防止 XSS
  linkify: true,
  breaks: true,
  highlight(code: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch {
        /* 高亮失败就退回纯文本转义 */
      }
    }
    return md.utils.escapeHtml(code)
  },
})

export function renderMarkdown(content: string): string {
  return md.render(content)
}
