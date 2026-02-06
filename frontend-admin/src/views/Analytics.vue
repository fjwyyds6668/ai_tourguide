<template>
  <div class="page-wrap">
    <h1 class="admin-page-title">数据分析</h1>
    <el-row v-if="interactionData" :gutter="16" style="margin: 24px 0">
      <el-col :span="12">
        <el-card>
          <el-statistic title="总交互次数" :value="interactionData.total">
            <template #prefix>
              <el-icon><ChatDotRound /></el-icon>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-bottom: 24px">
      <template #header>
        <span>热门景点</span>
        <span v-if="popularData?.visit_count_note" style="font-size: 12px; color: #666; margin-left: 12px">{{ popularData.visit_count_note }}</span>
      </template>
      <el-table
        :data="popularData?.popular_attractions || []"
        v-loading="loading"
        row-key="id"
      >
        <el-table-column prop="id" label="景点ID" width="100" />
        <el-table-column prop="name" label="景点名称" />
        <el-table-column prop="visit_count" label="访问次数" width="120" />
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <span>RAG 检索上下文日志（显示最近 5 条）</span>
      </template>
      <el-table :data="ragLogs" v-loading="ragLogsLoading" class="rag-logs-table">
        <el-table-column prop="timestamp" label="时间" width="180" />
        <el-table-column prop="use_rag" label="是否使用RAG" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.use_rag" type="success">RAG</el-tag>
            <el-tag v-else>Direct</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="query" label="用户问题" min-width="200" class-name="user-query-cell">
          <template #default="{ row }">
            <span class="user-query-text">{{ row.query || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RAG 检索&上下文" min-width="400" align="left">
          <template #default="{ row }">
            <div class="rag-context-wrap">
            <div class="rag-context">
              <div><strong>① 向量数据库命中（Milvus）</strong></div>
              <div v-if="!(row.rag_debug?.vector_results?.length)">
                <span style="color: #999">（无向量检索结果）</span>
              </div>
              <ol v-else style="padding-left: 20px; margin: 4px 0">
                <li v-for="(r, idx) in (row.rag_debug?.vector_results || []).slice(0, 5)" :key="idx">
                  text_id: <code>{{ r.text_id }}</code>，相似度: {{ (r.score ?? 0).toFixed(2) }}
                </li>
              </ol>
              <div><strong>② 图数据库命中（Neo4j）</strong></div>
              <div v-if="!(row.rag_debug?.graph_results?.length)">
                <span style="color: #999">（无图数据库检索结果）</span>
              </div>
              <ul v-else style="padding-left: 20px; margin: 4px 0">
                <li v-for="(r, idx) in (row.rag_debug?.graph_results || []).slice(0, 5)" :key="idx">
                  {{ nodeName(r.a) }} [{{ r.rel_type || '关联' }}] → {{ nodeName(r.b) }}
                </li>
              </ul>
              <div><strong>③ 组装后传给 LLM 的完整信息</strong></div>
              <div v-if="!(row.rag_debug?.final_sent_to_llm || row.rag_debug?.enhanced_context)" style="color: #999">（未构造上下文或未使用 RAG）</div>
              <pre v-else class="context-pre">{{ row.rag_debug?.final_sent_to_llm || row.rag_debug?.enhanced_context }}</pre>
              <div><strong>④ 大模型回复</strong></div>
              <div class="answer-preview">{{ row.final_answer_preview || '（本次未记录回复预览）' }}</div>
            </div>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ChatDotRound } from '@element-plus/icons-vue'
import api from '../api'

const loading = ref(false)
const ragLogsLoading = ref(false)
const interactionData = ref(null)
const popularData = ref(null)
const ragLogs = ref([])

const formatTime = (val) => {
  if (!val) return '—'
  const d = new Date(val)
  if (Number.isNaN(d.getTime())) return val
  const fmt = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai',
  })
  return fmt.format(d).replace(/\//g, '/')
}

function nodeName(n) {
  if (!n) return '节点'
  const p = n.properties || n
  return p.name || '节点'
}

const fetchRagLogs = async () => {
  ragLogsLoading.value = true
  try {
    const ragRes = await api.get('/admin/analytics/rag-logs', {
      params: { limit: 5 }
    })
    ragLogs.value = ragRes.data || []
  } catch (e) {
    console.error('获取 RAG 日志失败:', e)
  } finally {
    ragLogsLoading.value = false
  }
}

const fetchInteractions = async () => {
  loading.value = true
  try {
    const res = await api.get('/admin/analytics/interactions', {
      params: {
        skip: 0,
        limit: 5,
      },
    })
    const data = res.data || {}
    interactionData.value = data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const fetchPopular = async () => {
  try {
    const popularRes = await api.get('/admin/analytics/popular-attractions')
    popularData.value = popularRes.data
  } catch (e) {
    console.error(e)
  }
}

const fetchAnalytics = async () => {
  await Promise.all([fetchPopular(), fetchInteractions(), fetchRagLogs()])
}

onMounted(() => {
  fetchAnalytics()
})
</script>

<style scoped>
/* 确保 RAG 日志表格完全展开，无滚动限制 */
.rag-logs-table {
  overflow: visible;
}
.rag-logs-table :deep(.el-table__body-wrapper) {
  overflow: visible !important;
  max-height: none !important;
  height: auto !important;
}
.rag-logs-table :deep(.el-scrollbar__wrap) {
  overflow: visible !important;
  max-height: none !important;
  height: auto !important;
}
.rag-logs-table :deep(.el-scrollbar__view) {
  overflow: visible !important;
}
.rag-logs-table :deep(.el-table__body) {
  overflow: visible !important;
}
.rag-logs-table :deep(.el-table__row) {
  height: auto;
}
.rag-logs-table :deep(.el-table__cell) {
  padding: 12px 0;
  vertical-align: top;
}
/* 用户问题列完整显示，自动换行 */
.rag-logs-table :deep(.user-query-cell .cell) {
  white-space: normal;
  word-break: break-word;
  line-height: 1.4;
}
.user-query-text {
  display: block;
  white-space: normal;
  word-break: break-word;
}
/* RAG 检索&上下文：可滑动区域，内容过多时出现纵向滚动条 */
.rag-context-wrap {
  max-height: 360px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}
.rag-context-wrap::-webkit-scrollbar {
  width: 6px;
}
.rag-context-wrap::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}
.rag-context {
  font-size: 13px;
  white-space: normal;
  word-wrap: break-word;
  color: #000000;
}
.rag-context strong {
  color: #000000;
  font-weight: 600;
}
.rag-context > div {
  margin-bottom: 8px;
}
.context-pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: 4px;
  color: #000000;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  font-weight: inherit;
}
.answer-preview {
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: 4px;
  color: #000000;
}
.page-wrap {
  min-height: 200px;
}
.page-wrap .el-card {
  margin-bottom: 20px;
}
.page-wrap .el-card:last-child {
  margin-bottom: 0;
}

/* 最近交互表格样式优化 */
.recent-table :deep(.el-table__header-wrapper th) {
  font-size: 13px;
  color: #303133;
  font-weight: 600;
}
.recent-table :deep(.el-table__row) {
  height: auto;
}
.recent-table :deep(.el-table__cell) {
  padding: 6px 6px;
  font-size: 12px;
  line-height: 1.35;
  vertical-align: top;
}
.recent-table :deep(.el-table__cell .cell) {
  white-space: normal;
  word-break: break-word;
}
.sub-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 8px 0;
}
</style>
