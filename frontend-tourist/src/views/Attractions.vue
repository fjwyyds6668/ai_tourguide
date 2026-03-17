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
      
      <div class="attractions-body">
        <!-- 骨架屏：加载中 -->
        <el-row v-if="loading" :gutter="20">
          <el-col
            :xs="24" :sm="12" :md="8"
            v-for="n in pageSize" :key="'sk-' + n"
            class="attraction-col"
          >
            <el-card class="attraction-card skeleton-card">
              <el-skeleton animated>
                <template #template>
                  <el-skeleton-item variant="image" style="width:100%;height:200px;border-radius:4px" />
                  <div style="padding:8px 0 4px">
                    <el-skeleton-item variant="h3" style="width:60%" />
                    <el-skeleton-item variant="text" style="margin-top:8px" />
                    <el-skeleton-item variant="text" style="width:80%" />
                  </div>
                </template>
              </el-skeleton>
            </el-card>
          </el-col>
        </el-row>

        <!-- 正常展示 -->
        <el-row v-else-if="pagedAttractions.length > 0" :gutter="20">
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
                v-if="attraction.image_url && !failedImages.has(attraction.id)"
                :src="imageSrc(attraction.image_url)"
                class="attraction-image"
                alt="景点图片"
                loading="lazy"
                @error="failedImages.add(attraction.id)"
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
          v-else
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
    
    <el-dialog v-model="detailVisible" title="景点详情" :width="dialogWidth">
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
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'
import { Search, Picture } from '@element-plus/icons-vue'
import api from '../api'

const attractions = ref([])
const scenicSpots = ref([])
const selectedScenicId = ref(null)
const loading = ref(false)
const searchText = ref('')
const failedImages = reactive(new Set())
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
const _winW = ref(window.innerWidth)
let _winResizeTimer = null
const _onResize = () => {
  clearTimeout(_winResizeTimer)
  _winResizeTimer = setTimeout(() => { _winW.value = window.innerWidth }, 100)
}
onMounted(() => window.addEventListener('resize', _onResize, { passive: true }))
onUnmounted(() => { window.removeEventListener('resize', _onResize); clearTimeout(_winResizeTimer) })
const dialogWidth = computed(() => _winW.value <= 600 ? '92%' : '600px')

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
const CACHE_TTL_MS = 15 * 60_000 // 15分钟，景点列表在单次会话内几乎不变
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
  failedImages.clear()
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
  --el-card-bg-color: rgba(255, 255, 255, 0.45);
  border-radius: 12px;
  backdrop-filter: blur(18px) saturate(1.8);
  -webkit-backdrop-filter: blur(18px) saturate(1.8);
  border: 1px solid rgba(255, 255, 255, 0.60) !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
}
.page-card:hover {
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.15);
}
.page-card :deep(.el-card__body) {
  background: transparent !important;
}
.page-card :deep(.el-card__header) {
  padding: 14px 20px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.35);
  background: transparent !important;
}

.search-row {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 20px;
}

.search-input {
  width: 300px;
}
.search-row :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.45);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.55);
  box-shadow: none !important;
}
.search-row :deep(.el-input__wrapper:hover),
.search-row :deep(.el-input__wrapper.is-focus) {
  background: rgba(255, 255, 255, 0.60);
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
  color: #1a1a1a;
  font-weight: 700;
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
  --el-card-bg-color: rgba(255, 255, 255, 0.48);
  border-radius: 10px;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
  backdrop-filter: blur(12px) saturate(1.6);
  -webkit-backdrop-filter: blur(12px) saturate(1.6);
  border: 1px solid rgba(255, 255, 255, 0.55) !important;
}
.attraction-card :deep(.el-card__body) {
  background: transparent !important;
}
.attraction-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.15);
  --el-card-bg-color: rgba(255, 255, 255, 0.60);
}
.skeleton-card {
  cursor: default;
  pointer-events: none;
}
.skeleton-card:hover {
  transform: none !important;
  box-shadow: none !important;
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
  background: rgba(255, 255, 255, 0.3);
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

