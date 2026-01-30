<template>
  <div class="history-page">
    <el-card>
      <template #header>
        <h2>历史记录</h2>
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
        <el-table-column prop="interaction_type" label="类型" width="120" />
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无历史记录" />
        </template>
      </el-table>
      
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[5, 10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadHistory"
        @current-change="loadHistory"
        style="margin-top: 20px; justify-content: flex-end"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

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

const formatTime = (timeStr) => {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN')
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.history-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}
</style>

