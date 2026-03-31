<template>
  <div class="history-page">
    <el-card class="page-card">
      <template #header>
        <span class="card-title">对话记录</span>
      </template>

      <div v-if="noSessionData" class="no-session-tip">
        <el-empty description="暂无对话记录，前往语音导览开始对话吧" />
      </div>

      <template v-else>
        <div class="table-wrap desktop-only">
          <el-table
            :data="historyList"
            v-loading="loading"
            style="width: 100%; min-width: 600px"
            :row-key="(row) => row.id"
          >
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="query_text" label="用户问题" min-width="220" show-overflow-tooltip />
            <el-table-column label="回答" min-width="420">
              <template #default="{ row }">
                <div class="answer-full">{{ row.response_text || '—' }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="180">
              <template #default="{ row }">
                {{ formatTime(row.created_at) || row.created_at || '—' }}
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无对话记录" />
            </template>
          </el-table>
        </div>

        <div class="mobile-only" v-loading="loading">
          <el-empty v-if="historyList.length === 0" description="暂无对话记录" />
          <div v-for="row in historyList" :key="row.id" class="history-card">
            <div class="history-card-q">
              <span class="history-label">问：</span>{{ row.query_text || '—' }}
            </div>
            <div class="history-card-a">
              <span class="history-label">答：</span>{{ row.response_text || '—' }}
            </div>
            <div class="history-card-time">{{ formatTime(row.created_at) || row.created_at || '—' }}</div>
          </div>
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'
import api from '../api'
import { formatTime } from '../utils/format'

const historyList = ref([])
const loading = ref(false)

const getUserSessionIds = () => {
  try {
    return JSON.parse(localStorage.getItem('tourguide_session_ids') || '[]')
  } catch {
    return []
  }
}

const userSessionIds = ref(getUserSessionIds())
const noSessionData = computed(() => userSessionIds.value.length === 0)

const loadHistory = async () => {
  const ids = getUserSessionIds()
  userSessionIds.value = ids
  if (ids.length === 0) return

  loading.value = true
  try {
    const results = await Promise.all(
      ids.map(sid =>
        api.get('/history/history', {
          params: { session_id: sid, only_qa: true, skip: 0, limit: 200 }
        }).then(res => res.data?.data ?? res.data ?? []).catch(() => [])
      )
    )

    let merged = results.flat()

    // 回退：若 session_id 过滤无结果，加载全部记录（兜底）
    if (merged.length === 0) {
      const fallback = await api.get('/history/history', {
        params: { only_qa: true, skip: 0, limit: 200 }
      }).then(res => res.data?.data ?? res.data ?? []).catch(() => [])
      merged = fallback
    }

    const seen = new Set()
    merged = merged.filter(r => {
      if (seen.has(r.id)) return false
      seen.add(r.id)
      return true
    })
    merged.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))

    historyList.value = merged
  } catch (error) {
    ElMessage.error('加载对话记录失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.history-page {
  --rag-black: #000000;
  color: var(--rag-black);
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.history-page :deep(.el-table),
.history-page :deep(.el-table__header-wrapper th),
.history-page :deep(.el-table__header-wrapper th .cell),
.history-page :deep(.el-table__body-wrapper),
.history-page :deep(.el-table__cell),
.history-page :deep(.el-table__cell .cell),
.history-page :deep(.el-card__header),
.history-page :deep(.el-card__body) {
  color: var(--rag-black);
}

.history-page :deep(.el-table),
.history-page :deep(.el-table__inner-wrapper),
.history-page :deep(.el-table__header-wrapper),
.history-page :deep(.el-table__body-wrapper),
.history-page :deep(tr),
.history-page :deep(th.el-table__cell),
.history-page :deep(td.el-table__cell) {
  background: transparent !important;
}
.history-page :deep(.el-table__row:hover > td) {
  background: rgba(255, 255, 255, 0.35) !important;
}
.history-page :deep(.el-table__border-left-patch),
.history-page :deep(.el-table__border-bottom-patch) {
  background: transparent !important;
}

.page-card {
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.55) !important;
  backdrop-filter: blur(16px) saturate(1.8);
  -webkit-backdrop-filter: blur(16px) saturate(1.8);
  border: 1px solid rgba(255, 255, 255, 0.65);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.10);
}
.page-card:hover {
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.13);
}
.page-card :deep(.el-card__body) {
  background: transparent !important;
}
.history-page :deep(.el-table__row) {
  transition: background-color 0.1s ease;
}
@media (prefers-reduced-motion: reduce) {
  .history-page :deep(.el-table__row) { transition: none; }
}

.page-card :deep(.el-card__header) {
  padding: 14px 20px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.4);
  background: transparent !important;
}

.card-title {
  font-size: 16px;
  color: var(--rag-black);
}

.table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.answer-full {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}


.no-session-tip {
  padding: 40px 0;
}

.desktop-only { display: block; }
.mobile-only  { display: none; }

@media (max-width: 640px) {
  .desktop-only { display: none; }
  .mobile-only  { display: block; }
  .history-page { padding: 12px; }
}

.history-card {
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.65);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
  word-break: break-word;
}

.history-card-q {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 6px;
  line-height: 1.5;
}

.history-card-a {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  white-space: pre-wrap;
  margin-bottom: 8px;
}

.history-label {
  color: #409eff;
  font-weight: 700;
  margin-right: 2px;
}

.history-card-time {
  font-size: 12px;
  color: #909399;
  text-align: right;
}
</style>
