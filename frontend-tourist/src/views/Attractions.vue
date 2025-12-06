<template>
  <div class="attractions">
    <el-card>
      <template #header>
        <h2>景点列表</h2>
      </template>
      
      <el-input
        v-model="searchText"
        placeholder="搜索景点..."
        style="margin-bottom: 20px"
        clearable
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      
      <el-row :gutter="20" v-loading="loading">
        <el-col
          :span="8"
          v-for="attraction in filteredAttractions"
          :key="attraction.id"
          style="margin-bottom: 20px"
        >
          <el-card shadow="hover" @click="viewDetails(attraction)">
            <img
              v-if="attraction.image_url"
              :src="attraction.image_url"
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
    </el-card>
    
    <el-dialog v-model="detailVisible" title="景点详情" width="600px">
      <div v-if="selectedAttraction">
        <h3>{{ selectedAttraction.name }}</h3>
        <p><strong>位置：</strong>{{ selectedAttraction.location }}</p>
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
const loading = ref(false)
const searchText = ref('')
const detailVisible = ref(false)
const selectedAttraction = ref(null)

const filteredAttractions = computed(() => {
  if (!searchText.value) {
    return attractions.value
  }
  return attractions.value.filter(attraction =>
    attraction.name.toLowerCase().includes(searchText.value.toLowerCase()) ||
    (attraction.description && attraction.description.toLowerCase().includes(searchText.value.toLowerCase()))
  )
})

const fetchAttractions = async () => {
  loading.value = true
  try {
    const res = await api.get('/attractions')
    attractions.value = res.data
  } catch (error) {
    ElMessage.error('加载景点失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const viewDetails = (attraction) => {
  selectedAttraction.value = attraction
  detailVisible.value = true
}

onMounted(() => {
  fetchAttractions()
})
</script>

<style scoped>
.attractions {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
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
  color: #666;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>

