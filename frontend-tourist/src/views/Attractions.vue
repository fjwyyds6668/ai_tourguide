<template>
  <div class="attractions">
    <el-card class="page-card">
      <template #header>
        <span class="card-title">景点列表</span>
      </template>
      
      <div class="search-row">
        <el-input
          v-model="searchText"
          placeholder="搜索景点..."
          clearable
          class="search-input"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>
      
      <div v-loading="loading" class="attractions-body">
        <el-row v-if="filteredAttractions.length > 0" :gutter="20">
          <el-col
            :span="8"
            v-for="attraction in filteredAttractions"
            :key="attraction.id"
            class="attraction-col"
          >
            <el-card shadow="hover" class="attraction-card" @click="viewDetails(attraction)">
              <img
                v-if="attraction.image_url"
                :src="imageSrc(attraction.image_url)"
                class="attraction-image"
                alt="景点图片"
              />
              <div v-else class="placeholder-image">
                <el-icon :size="48"><Picture /></el-icon>
              </div>
              <h3>{{ attraction.name }}</h3>
              <p class="description">{{ attraction.description }}</p>
              <el-tag v-if="attraction.category">{{ attraction.category }}</el-tag>
            </el-card>
          </el-col>
        </el-row>
        <el-empty
          v-else-if="!loading"
          :description="selectedScenicId ? '该景区暂无景点' : '请先选择景区'"
          style="padding: 40px 0"
        />
      </div>
    </el-card>
    
    <el-dialog v-model="detailVisible" title="景点详情" width="600px">
      <div v-if="selectedAttraction">
        <h3>{{ selectedAttraction.name }}</h3>
        <p v-if="selectedAttraction.location"><strong>位置：</strong>{{ selectedAttraction.location }}</p>
        <p><strong>描述：</strong>{{ selectedAttraction.description }}</p>
        <div v-if="selectedAttraction.audio_url">
          <audio :src="selectedAttraction.audio_url" controls></audio>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Picture } from '@element-plus/icons-vue'
import api from '../api'

const attractions = ref([])
const scenicSpots = ref([])
const selectedScenicId = ref(null)
const loading = ref(false)
const searchText = ref('')
const detailVisible = ref(false)
const selectedAttraction = ref(null)

const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || 'http://localhost:18000'

const imageSrc = (url) => {
  if (!url) return ''
  // 后端返回形如 /uploads/images/xxx.jpg 的相对路径，需要拼上后端地址
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }
  return `${backendOrigin}${url}`
}

const filteredAttractions = computed(() => {
  // 未选择景区时不展示任何景点，提示用户先选景区
  if (!selectedScenicId.value) {
    return []
  }
  let list = attractions.value
  if (searchText.value) {
    const kw = searchText.value.toLowerCase()
    list = list.filter(attraction =>
      attraction.name.toLowerCase().includes(kw) ||
      (attraction.description && attraction.description.toLowerCase().includes(kw))
    )
  }
  return list
})

const fetchAttractions = async () => {
  loading.value = true
  try {
    const params = {}
    if (selectedScenicId.value) {
      params.scenic_spot_id = selectedScenicId.value
    }
    const res = await api.get('/attractions', { params })
    attractions.value = res.data
  } catch (error) {
    ElMessage.error('加载景点失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const onScenicChange = () => {}

const viewDetails = (attraction) => {
  selectedAttraction.value = attraction
  detailVisible.value = true
}

onMounted(async () => {
  try {
    const res = await api.get('/attractions/scenic-spots')
    scenicSpots.value = res.data || []
  } catch (error) {
    console.error(error)
  }
  const savedId = localStorage.getItem('current_scenic_spot_id')
  if (savedId) {
    const idNum = Number(savedId)
    if (!Number.isNaN(idNum)) {
      selectedScenicId.value = idNum
    }
  }
  await fetchAttractions()
})
</script>

<style scoped>
.attractions {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.page-card {
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.page-card :deep(.el-card__header) {
  padding: 14px 20px;
  font-weight: 600;
  border-bottom: 1px solid #f0f0f0;
}

.search-row {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 20px;
}

.search-input {
  width: 300px;
}

.card-title {
  font-size: 16px;
  color: #303133;
}

.attractions-body {
  min-height: 200px;
}

.attraction-col {
  margin-bottom: 20px;
}

.attraction-card {
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.attraction-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.attraction-image {
  width: 100%;
  height: 200px;
  object-fit: cover;
  border-radius: 4px;
}

.placeholder-image {
  width: 100%;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 4px;
}

.description {
  color: #606266;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>

