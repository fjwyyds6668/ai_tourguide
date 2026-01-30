/**
 * 格式化时间字符串为本地化显示
 * @param {string} timeStr - ISO 或可被 Date 解析的时间字符串
 * @returns {string}
 */
export function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN')
}
