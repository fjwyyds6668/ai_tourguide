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
        max-height="360"
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
      <el-table
        :data="ragLogs"
        v-loading="ragLogsLoading"
        class="rag-logs-table"
        row-key="id"
        max-height="520"
      >
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
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
        <el-table-column label="摘要" min-width="260">
          <template #default="{ row }">
            <div class="summary">
              <div>
                <strong>向量命中</strong>：{{ (row.rag_debug?.vector_results || []).length }}
                <span style="margin-left: 10px"><strong>图命中</strong>：{{ (row.rag_debug?.graph_results || []).length }}</span>
              </div>
              <div class="answer-preview">{{ row.final_answer_preview || '（本次未记录回复预览）' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" title="RAG 日志详情" width="900px" destroy-on-close>
      <div v-if="detailRow" class="detail">
        <div class="detail-line"><strong>时间：</strong>{{ formatTime(detailRow.timestamp) }}</div>
        <div class="detail-line"><strong>是否 RAG：</strong>{{ detailRow.use_rag ? 'RAG' : 'Direct' }}</div>
        <div class="detail-line"><strong>用户问题：</strong>{{ detailRow.query || '—' }}</div>
        <div class="detail-block">
          <div class="detail-title">① 向量数据库命中（Milvus）</div>
          <div v-if="!(detailRow.rag_debug?.vector_results?.length)" style="color: #999">（无向量检索结果）</div>
          <ol v-else style="padding-left: 20px; margin: 6px 0">
            <li v-for="(r, idx) in (detailRow.rag_debug?.vector_results || []).slice(0, 20)" :key="idx">
              text_id: <code>{{ r.text_id }}</code>，相似度: {{ (r.score ?? 0).toFixed(2) }}
            </li>
          </ol>
        </div>
        <div class="detail-block">
          <div class="detail-title">② 图数据库命中（Neo4j）</div>
          <div v-if="!(detailRow.rag_debug?.graph_results?.length)" style="color: #999">（无图数据库检索结果）</div>
          <ul v-else style="padding-left: 20px; margin: 6px 0">
            <li v-for="(r, idx) in (detailRow.rag_debug?.graph_results || []).slice(0, 20)" :key="idx">
              {{ nodeName(r.a) }} [{{ r.rel_type || '关联' }}] → {{ nodeName(r.b) }}
            </li>
          </ul>
        </div>
        <div class="detail-block">
          <div class="detail-title">③ 组装后传给 LLM 的完整信息</div>
          <div v-if="!(detailRow.rag_debug?.final_sent_to_llm || detailRow.rag_debug?.enhanced_context)" style="color: #999">（未构造上下文或未使用 RAG）</div>
          <pre v-else class="context-pre">{{ detailRow.rag_debug?.final_sent_to_llm || detailRow.rag_debug?.enhanced_context }}</pre>
        </div>
        <div class="detail-block">
          <div class="detail-title">④ 大模型回复</div>
          <pre class="context-pre">{{ detailRow.final_answer_preview || '（本次未记录回复预览）' }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ChatDotRound } from '@element-plus/icons-vue'
import api, { withAbort, cancelInflight } from '../api'

const loading = ref(false)
const ragLogsLoading = ref(false)
const interactionData = ref(null)
const popularData = ref(null)
const ragLogs = ref([])
const detailVisible = ref(false)
const detailRow = ref(null)

const openDetail = (row) => {
  detailRow.value = row || null
  detailVisible.value = true
}

const formatTime = (val) => {
  if (!val) return '—'
  const d = new Date(val)
  if (Number.isNaN(d.getTime())) return val
  const parts = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai',
  }).formatToParts(d)
  const get = (type) => parts.find(p => p.type === type)?.value || ''
  const y = get('year')
  const m = get('month')
  const day = get('day')
  const hh = get('hour')
  const mm = get('minute')
  const ss = get('second')
  if (!y || !m || !day || !hh || !mm || !ss) return val
  return `${y}/${m}/${day} ${hh}:${mm}:${ss}`
}

function nodeName(n) {
  if (!n) return '节点'
  const p = n.properties || n
  return p.name || '节点'
}

const fetchAnalytics = async (silent = false) => {
  if (fetchAnalytics._inFlight) return
  fetchAnalytics._inFlight = true
  if (!silent) {
    loading.value = true
    ragLogsLoading.value = true
  }
  try {
    const res = await api.get('/admin/analytics/dashboard', {
      params: { rag_limit: 5, interactions_limit: 5 },
      ...withAbort('admin:analytics:dashboard'),
    })
    const data = res.data || {}
    ragLogs.value = data.rag_logs || []
    interactionData.value = data.interactions || null
    popularData.value = data.popular_attractions || null
  } catch (e) {
    // 被取消的请求不算失败
    if (e?.name !== 'CanceledError' && e?.code !== 'ERR_CANCELED') {
      console.error('获取数据分析失败:', e)
      throw e
    }
  } finally {
    if (!silent) {
      loading.value = false
      ragLogsLoading.value = false
    }
    fetchAnalytics._inFlight = false
  }
}

let refreshTimer = null
let visibilityHandler = null
let pollDelayMs = 5000
let stopped = false

function startPolling() {
  if (refreshTimer) return
  stopped = false
  const tick = async () => {
    if (stopped) return
    try {
      await fetchAnalytics(true)
      pollDelayMs = 5000
    } catch (_) {
      // 失败指数退避，最多60s
      pollDelayMs = Math.min(60000, Math.max(5000, pollDelayMs * 2))
    }
    refreshTimer = setTimeout(tick, pollDelayMs)
  }
  refreshTimer = setTimeout(tick, pollDelayMs)
}
function stopPolling() {
  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
  stopped = true
  cancelInflight('admin:analytics:dashboard')
}

onMounted(() => {
  fetchAnalytics(false) // 首次加载显示 loading
  if (document.visibilityState === 'visible') startPolling()
  visibilityHandler = () => {
    if (document.visibilityState === 'visible') {
      fetchAnalytics(true)
      startPolling()
    } else {
      stopPolling()
    }
  }
  document.addEventListener('visibilitychange', visibilityHandler)
})

onUnmounted(() => {
  stopPolling()
  if (visibilityHandler) {
    document.removeEventListener('visibilitychange', visibilityHandler)
    visibilityHandler = null
  }
})
</script>

<style scoped>
.page-wrap {
  --rag-black: #000000;
  color: var(--rag-black);
}

.page-wrap :deep(.el-table),
.page-wrap :deep(.el-table__header-wrapper th),
.page-wrap :deep(.el-table__header-wrapper th .cell),
.page-wrap :deep(.el-table__body-wrapper),
.page-wrap :deep(.el-table__cell),
.page-wrap :deep(.el-table__cell .cell),
.page-wrap :deep(.el-statistic__head),
.page-wrap :deep(.el-statistic__number),
.page-wrap :deep(.el-card__header),
.page-wrap :deep(.el-card__body) {
  color: var(--rag-black);
}

.rag-logs-table :deep(.el-table__row) {
  height: auto;
}
.rag-logs-table :deep(.el-table__cell) {
  padding: 12px 0;
  vertical-align: top;
}
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
.context-pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: 4px;
  color: var(--rag-black);
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  font-weight: inherit;
}
.answer-preview {
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: 4px;
  color: var(--rag-black);
  display: -webkit-box;
  line-clamp: 3;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.summary {
  font-size: 13px;
  color: var(--rag-black);
}
.detail {
  font-size: 13px;
  color: var(--rag-black);
}
.detail-line {
  margin-bottom: 8px;
}
.detail-block {
  margin-top: 12px;
}
.detail-title {
  font-weight: 600;
  margin-bottom: 6px;
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
