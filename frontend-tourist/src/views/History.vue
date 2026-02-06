<template>
  <div class="history-page">
    <el-card class="page-card">
      <template #header>
        <span class="card-title">历史记录</span>
      </template>
      
      <el-table
        :data="historyList"
        v-loading="loading"
        style="width: 100%"
        stripe
        :row-key="(row) => row.id"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="query_text" label="问题" min-width="200" />
        <el-table-column prop="response_text" label="回答" min-width="300" />
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无历史记录" />
        </template>
      </el-table>
      
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[5, 10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadHistory"
          @current-change="loadHistory"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import { formatTime } from '../utils/format'

const historyList = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(5)
const total = ref(0)

const loadHistory = async () => {
  loading.value = true
  try {
    const res = await api.get('/history/history', {
      params: {
        skip: (currentPage.value - 1) * pageSize.value,
        limit: pageSize.value
      }
    })
    // 接口返回 { data: [...], total: 总数 }
    historyList.value = res.data?.data ?? res.data ?? []
    total.value = res.data?.total ?? 0
  } catch (error) {
    ElMessage.error('加载历史记录失败')
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
  /* 统一游客端历史记录页“黑色字”颜色（与管理端 RAG 板块一致） */
  --rag-black: #000000;
  color: var(--rag-black);
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

/* Element Plus 默认文本色覆盖：表格/分页/卡片标题等统一为 rag-black */
.history-page :deep(.el-table),
.history-page :deep(.el-table__header-wrapper th),
.history-page :deep(.el-table__header-wrapper th .cell),
.history-page :deep(.el-table__body-wrapper),
.history-page :deep(.el-table__cell),
.history-page :deep(.el-table__cell .cell),
.history-page :deep(.el-card__header),
.history-page :deep(.el-card__body),
.history-page :deep(.el-pagination),
.history-page :deep(.el-pagination__total),
.history-page :deep(.el-pagination__sizes),
.history-page :deep(.el-pagination__jump) {
  color: var(--rag-black);
}

.page-card {
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.page-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
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
  border-bottom: 1px solid #f0f0f0;
}

.card-title {
  font-size: 16px;
  color: var(--rag-black);
}

.pagination-wrap {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>

