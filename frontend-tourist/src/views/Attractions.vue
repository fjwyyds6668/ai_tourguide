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
        <el-row v-if="pagedAttractions.length > 0" :gutter="20">
          <el-col
            :xs="24"
            :sm="12"
            :md="8"
            v-for="attraction in pagedAttractions"
            :key="attraction.id"
            class="attraction-col"
          >
            <el-card shadow="hover" class="attraction-card" @click="viewDetails(attraction)">
              <img
                v-if="attraction.image_url"
                :src="imageSrc(attraction.image_url)"
                class="attraction-image"
                alt="景点图片"
                loading="lazy"
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

      <div v-if="selectedScenicId && filteredAttractions.length > 0" class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[9, 12, 18, 24]"
          :total="filteredAttractions.length"
          layout="total, sizes, prev, pager, next"
          background
        />
      </div>
    </el-card>
    
    <el-dialog v-model="detailVisible" title="景点详情" width="600px">
      <div v-if="selectedAttraction">
        <h3>{{ selectedAttraction.name }}</h3>
        <p v-if="selectedAttraction.location"><strong>位置：</strong>{{ selectedAttraction.location }}</p>
        <div class="detail-image-wrap">
          <img
            v-if="selectedAttraction.image_url"
            :src="imageSrc(selectedAttraction.image_url)"
            class="detail-image"
            alt="景点图片"
            loading="eager"
          />
          <div v-else class="detail-placeholder-image">
            <el-icon :size="56"><Picture /></el-icon>
          </div>
        </div>
        <p><strong>描述：</strong>{{ selectedAttraction.description }}</p>
        <div v-if="selectedAttraction.audio_url">
          <audio :src="selectedAttraction.audio_url" controls></audio>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Picture } from '@element-plus/icons-vue'
import api from '../api'

const attractions = ref([])
const scenicSpots = ref([])
const selectedScenicId = ref(null)
const loading = ref(false)
const searchText = ref('')
const searchKeyword = ref('')
let searchDebounceTimer = null
watch(searchText, (val) => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    searchKeyword.value = val
    searchDebounceTimer = null
  }, 200)
}, { immediate: true })

const detailVisible = ref(false)
const selectedAttraction = ref(null)

const page = ref(1)
const pageSize = ref(12)

const imageSrc = (url) => {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  if (url.startsWith('/')) return url
  const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || 'http://localhost:18000'
  return `${backendOrigin}${url}`
}

const filteredAttractions = computed(() => {
  if (!selectedScenicId.value) return []
  let list = attractions.value
  const kw = (searchKeyword.value || '').trim().toLowerCase()
  if (kw) {
    list = list.filter(attraction =>
      attraction.name.toLowerCase().includes(kw) ||
      (attraction.description && attraction.description.toLowerCase().includes(kw))
    )
  }
  return list
})

const pagedAttractions = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredAttractions.value.slice(start, start + pageSize.value)
})

watch([selectedScenicId, searchKeyword, pageSize], () => {
  page.value = 1
})

// short-lived cache to avoid re-fetching the same scenic spot on back-navigation
const _attractionsCache = new Map() // scenicId -> { ts, data }
const CACHE_TTL_MS = 60_000
let attractionsAbortController = null

const fetchAttractions = async () => {
  if (!selectedScenicId.value) {
    attractions.value = []
    return
  }

  const scenicId = selectedScenicId.value
  const cached = _attractionsCache.get(scenicId)
  const now = Date.now()
  if (cached && now - cached.ts < CACHE_TTL_MS) {
    attractions.value = cached.data
    return
  }

  loading.value = true
  try {
    try { attractionsAbortController?.abort() } catch (_) {}
    attractionsAbortController = typeof AbortController !== 'undefined' ? new AbortController() : null

    const res = await api.get('/attractions', {
      params: { scenic_spot_id: scenicId },
      signal: attractionsAbortController?.signal,
    })
    const data = res.data || []
    attractions.value = data
    _attractionsCache.set(scenicId, { ts: Date.now(), data })
  } catch (error) {
    if (error?.name !== 'CanceledError' && error?.code !== 'ERR_CANCELED') {
      ElMessage.error('加载景点失败')
      console.error(error)
    }
  } finally {
    loading.value = false
  }
}

const onScenicChange = () => {}

const viewDetails = async (attraction) => {
  selectedAttraction.value = attraction
  detailVisible.value = true
  try {
    const res = await api.get(`/attractions/${attraction.id}`)
    if (res?.data) selectedAttraction.value = res.data
  } catch (e) {
  }
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

watch(selectedScenicId, async (id) => {
  if (!id) return
  localStorage.setItem('current_scenic_spot_id', String(id))
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
.page-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
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
@media (max-width: 768px) {
  .attractions {
    padding: 12px;
  }
  .search-row .search-input {
    width: 100%;
  }
  .search-row .search-input :deep(.el-input__inner) {
    font-size: 16px;
  }
}

.card-title {
  font-size: 16px;
  color: #303133;
}

.attractions-body {
  min-height: 200px;
}
.pager {
  display: flex;
  justify-content: center;
  padding-top: 12px;
}

.attraction-col {
  margin-bottom: 20px;
}

.attraction-card {
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.12s ease;
}

.attraction-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
@media (prefers-reduced-motion: reduce) {
  .attraction-card { transition: none; }
  .attraction-card:hover { transform: none; }
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
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.detail-image-wrap {
  margin: 12px 0 10px;
}
.detail-image {
  width: 100%;
  max-height: 320px;
  object-fit: cover;
  border-radius: 10px;
  display: block;
  background: #f5f7fa;
}
.detail-placeholder-image {
  width: 100%;
  height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 10px;
  color: #9aa0a6;
}
</style>

