<template>
  <div class="dashboard-page">
    <h1 class="admin-page-title">仪表盘</h1>
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="24" :md="8" :lg="8">
        <el-card class="stat-card stat-card-users" shadow="hover">
          <el-statistic title="管理员数" :value="stats.total_users">
            <template #prefix>
              <span class="stat-icon"><el-icon><User /></el-icon></span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="8" :lg="8">
        <el-card class="stat-card stat-card-attractions" shadow="hover">
          <el-statistic title="景点数量" :value="stats.attractions_count">
            <template #prefix>
              <span class="stat-icon"><el-icon><Location /></el-icon></span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="8" :lg="8">
        <el-card class="stat-card stat-card-interactions" shadow="hover">
          <el-statistic title="交互次数" :value="stats.interactions_count">
            <template #prefix>
              <span class="stat-icon"><el-icon><ChatDotRound /></el-icon></span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { User, Location, ChatDotRound } from '@element-plus/icons-vue'
import api from '../api'

const loading = ref(false)
const stats = ref({
  total_users: 0,
  attractions_count: 0,
  interactions_count: 0,
})

onMounted(async () => {
  loading.value = true
  try {
    const res = await api.get('/admin/stats')
    stats.value = res.data
  } catch (error) {
    console.error(error)
    ElMessage.error('获取仪表盘统计失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dashboard-page {
  min-height: 200px;
}
.stats-row {
  margin-top: 8px;
}
.stats-row .el-col {
  margin-bottom: 20px;
}
.stat-card {
  padding: 4px 0;
}
.stat-card :deep(.el-statistic__head) {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 8px;
}
.stat-card :deep(.el-statistic__content) {
  font-size: 28px;
  font-weight: 600;
  color: #1f2937;
}
.stat-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  margin-right: 12px;
}
.stat-card-users .stat-icon {
  background: #eef2ff;
  color: #4f46e5;
}
.stat-card-attractions .stat-icon {
  background: #ecfdf5;
  color: #059669;
}
.stat-card-interactions .stat-icon {
  background: #fef3c7;
  color: #d97706;
}
</style>
