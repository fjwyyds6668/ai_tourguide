<template>
  <div class="dashboard-page">
    <h1 class="admin-page-title">仪表盘</h1>

    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="12" :md="12" :lg="12">
        <el-card class="stat-card stat-card-users" shadow="hover">
          <el-statistic title="管理员数" :value="stats.total_users">
            <template #prefix>
              <span class="stat-icon"><el-icon><User /></el-icon></span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="12" :lg="12">
        <el-card class="stat-card stat-card-interactions" shadow="hover">
          <el-statistic title="交互次数" :value="stats.interactions_count" :formatter="(v) => v">
            <template #prefix>
              <span class="stat-icon"><el-icon><ChatDotRound /></el-icon></span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <div class="section-header">
      <span class="section-title">
        <el-icon class="section-icon"><MapLocation /></el-icon>
        景区 &amp; 景点总览
      </span>
      <span class="section-meta">
        {{ scenicSpots.length }} 个景区 · {{ allAttractions.length }} 个景点
      </span>
    </div>

    <div v-if="spotsLoading" class="spots-skeleton">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else class="spots-grid">
      <el-card
        v-for="spot in scenicSpots"
        :key="spot.id"
        class="spot-card"
        shadow="hover"
      >
        <template #header>
          <div class="spot-card-header">
            <el-icon class="spot-header-icon"><Promotion /></el-icon>
            <span class="spot-name">{{ spot.name }}</span>
            <el-tag size="small" type="success" class="spot-count-tag">
              {{ attractionsBySpot[spot.id]?.length || 0 }} 个景点
            </el-tag>
          </div>
        </template>

        <div v-if="attractionsBySpot[spot.id]?.length" class="attraction-list">
          <div
            v-for="(a, idx) in attractionsBySpot[spot.id]"
            :key="a.id"
            class="attraction-item"
          >
            <span class="attraction-index">{{ idx + 1 }}</span>
            <span class="attraction-name">{{ a.name }}</span>
            <el-tag
              v-if="a.category"
              size="small"
              class="attraction-category"
              type="info"
              effect="plain"
            >{{ a.category }}</el-tag>
          </div>
        </div>
        <div v-else class="no-attractions">
          <el-icon><InfoFilled /></el-icon> 暂无景点
        </div>
      </el-card>

      <el-card
        v-if="unassignedAttractions.length"
        class="spot-card spot-card-unassigned"
        shadow="hover"
      >
        <template #header>
          <div class="spot-card-header">
            <el-icon class="spot-header-icon unassigned-icon"><QuestionFilled /></el-icon>
            <span class="spot-name">未归属景区</span>
            <el-tag size="small" type="warning" class="spot-count-tag">
              {{ unassignedAttractions.length }} 个景点
            </el-tag>
          </div>
        </template>
        <div class="attraction-list">
          <div
            v-for="(a, idx) in unassignedAttractions"
            :key="a.id"
            class="attraction-item"
          >
            <span class="attraction-index">{{ idx + 1 }}</span>
            <span class="attraction-name">{{ a.name }}</span>
            <el-tag
              v-if="a.category"
              size="small"
              class="attraction-category"
              type="info"
              effect="plain"
            >{{ a.category }}</el-tag>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { User, ChatDotRound, MapLocation, Promotion, InfoFilled, QuestionFilled } from '@element-plus/icons-vue'
import api from '../api'

const loading = ref(false)
const spotsLoading = ref(false)
const stats = ref({
  total_users: 0,
  attractions_count: 0,
  interactions_count: 0,
})
const scenicSpots = ref([])
const allAttractions = ref([])

const attractionsBySpot = computed(() => {
  const map = {}
  for (const a of allAttractions.value) {
    const sid = a.scenic_spot_id
    if (sid != null) {
      if (!map[sid]) map[sid] = []
      map[sid].push(a)
    }
  }
  return map
})

const unassignedAttractions = computed(() =>
  allAttractions.value.filter(a => a.scenic_spot_id == null)
)

onMounted(async () => {
  loading.value = true
  spotsLoading.value = true
  try {
    const [statsRes, spotsRes, attractionsRes] = await Promise.all([
      api.get('/admin/stats'),
      api.get('/attractions/scenic-spots'),
      api.get('/attractions', { params: { limit: 500 } }),
    ])
    stats.value = statsRes.data
    scenicSpots.value = spotsRes.data || []
    allAttractions.value = attractionsRes.data || []
  } catch (error) {
    console.error(error)
    ElMessage.error('获取仪表盘数据失败')
  } finally {
    loading.value = false
    spotsLoading.value = false
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
  transition: transform 0.12s ease;
}
.stat-card:hover {
  transform: translateY(-2px);
}
@media (prefers-reduced-motion: reduce) {
  .stat-card { transition: none; }
  .stat-card:hover { transform: none; }
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
.stat-card-interactions .stat-icon {
  background: #fef3c7;
  color: #d97706;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 4px 0 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}
.section-icon {
  color: #059669;
  font-size: 18px;
}
.section-meta {
  font-size: 13px;
  color: #9ca3af;
}

.spots-skeleton {
  padding: 16px;
}

.spots-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.spot-card {
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.spot-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08) !important;
}
@media (prefers-reduced-motion: reduce) {
  .spot-card { transition: none; }
  .spot-card:hover { transform: none; }
}
.spot-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border-bottom: 1px solid #d1fae5;
}
.spot-card-unassigned :deep(.el-card__header) {
  background: linear-gradient(135deg, #fffbeb 0%, #fef9c3 100%);
  border-bottom: 1px solid #fde68a;
}
.spot-card :deep(.el-card__body) {
  padding: 12px 16px;
}

.spot-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.spot-header-icon {
  color: #059669;
  font-size: 16px;
  flex-shrink: 0;
}
.unassigned-icon {
  color: #d97706;
}
.spot-name {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.spot-count-tag {
  flex-shrink: 0;
}

.attraction-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.attraction-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: #f9fafb;
  transition: background 0.1s;
}
.attraction-item:hover {
  background: #f3f4f6;
}
.attraction-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #e0e7ff;
  color: #4f46e5;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.attraction-name {
  flex: 1;
  font-size: 13px;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attraction-category {
  flex-shrink: 0;
  font-size: 11px;
}
.no-attractions {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #9ca3af;
  font-size: 13px;
  padding: 8px 0;
}
</style>
