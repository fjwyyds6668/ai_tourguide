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

    <el-card title="最近交互记录" style="margin-bottom: 24px">
      <template #header>最近交互记录</template>
      <el-table
        :data="interactionData?.recent_interactions || []"
        v-loading="loading"
        row-key="id"
        max-height="400"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="session_id" label="会话ID" width="120" />
        <el-table-column prop="query_text" label="查询内容" min-width="200" show-overflow-tooltip />
        <el-table-column prop="interaction_type" label="交互类型" width="120" />
        <el-table-column prop="created_at" label="时间" width="180" />
      </el-table>
    </el-card>

    <el-card title="RAG 检索上下文日志（传给 LLM 的信息）">
      <template #header>RAG 检索上下文日志（传给 LLM 的信息）</template>
      <el-table :data="ragLogs" v-loading="ragLogsLoading" class="rag-logs-table">
        <el-table-column prop="timestamp" label="时间" width="180" />
        <el-table-column prop="use_rag" label="是否使用RAG" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.use_rag" type="success">RAG</el-tag>
            <el-tag v-else>Direct</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="query" label="用户问题" width="260" show-overflow-tooltip />
        <el-table-column label="RAG 检索&上下文" min-width="400" align="left">
          <template #default="{ row }">
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

const fetchAnalytics = async () => {
  loading.value = true
  try {
    const [interactionsRes, popularRes] = await Promise.all([
      api.get('/admin/analytics/interactions'),
      api.get('/admin/analytics/popular-attractions'),
    ])
    interactionData.value = interactionsRes.data
    popularData.value = popularRes.data
    await fetchRagLogs()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
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
.rag-context {
  font-size: 13px;
  white-space: normal;
  word-wrap: break-word;
}
.rag-context > div {
  margin-bottom: 8px;
}
.context-pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: 4px;
  padding: 8px;
  background: #fafafa;
  border-radius: 4px;
  font-size: 12px;
  max-width: 100%;
  overflow: visible;
}
.answer-preview {
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: 4px;
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
</style>
