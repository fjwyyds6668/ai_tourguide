/** ISO/可解析时间字符串 -> 本地化显示 */
export function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN')
}
