<template>
  <div class="home" :class="{ 'has-background': backgroundImageUrl }" :style="backgroundImageUrl ? { '--bg-image': `url(${backgroundImageUrl})` } : {}">
    <el-card class="home-card">
      <template #header>
        <div class="card-header">
          <span>请选择您所在的景区</span>
        </div>
      </template>
      <div class="scenic-select-wrapper">
        <el-select
          v-model="selectedScenicId"
          placeholder="请选择景区"
          size="large"
          style="width: 320px"
          @change="handleScenicChange"
        >
          <el-option
            v-for="spot in scenicSpots"
            :key="spot.id"
            :label="spot.name"
            :value="spot.id"
          />
        </el-select>
      </div>

      <el-row :gutter="20" class="feature-cards" style="margin-top: 24px">
        <el-col :span="8" class="feature-col">
          <el-card
            shadow="hover"
            :class="{ disabled: !selectedScenicId }"
            @click="navigateIfSelected('/voice-guide')"
          >
            <el-icon :size="48"><Microphone /></el-icon>
            <h3>语音导览</h3>
            <p>与 AI 导游进行实时语音交互</p>
          </el-card>
        </el-col>
        <el-col :span="8" class="feature-col">
          <el-card
            shadow="hover"
            :class="{ disabled: !selectedScenicId }"
            @click="navigateIfSelected('/attractions')"
          >
            <el-icon :size="48"><Location /></el-icon>
            <h3>景点浏览</h3>
            <p>查看该景区下的所有景点</p>
          </el-card>
        </el-col>
        <el-col :span="8" class="feature-col">
          <el-card
            shadow="hover"
            :class="{ disabled: !selectedScenicId }"
            @click="navigateIfSelected('/history')"
          >
            <el-icon :size="48"><Document /></el-icon>
            <h3>历史记录</h3>
            <p>查看在当前景区的对话记录</p>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Microphone, Location, Document } from '@element-plus/icons-vue'
import api from '../api'

const router = useRouter()
const scenicSpots = ref([])
const selectedScenic = ref(null)
const selectedScenicId = ref(null)

const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || 'http://localhost:18000'

const backgroundImageUrl = computed(() => {
  const url = selectedScenic.value?.cover_image_url
  if (!url) {
    return ''
  }
  return url.startsWith('http://') || url.startsWith('https://')
    ? url
    : `${backendOrigin}${url}`
})

watch(backgroundImageUrl, async (url) => {
  await nextTick()
  const mainEl = document.querySelector('.el-main.main-with-header')
  if (mainEl) {
    if (url) {
      mainEl.style.background = 'transparent'
    } else {
      mainEl.style.background = '#f5f7fa'
    }
  }
}, { immediate: true })

onMounted(async () => {
  try {
    const res = await api.get('/attractions/scenic-spots')
    scenicSpots.value = res.data || []
    // 不默认选中景区，由用户进入首页后自行选择
  } catch (e) {
    console.error('加载景区列表失败:', e)
  }
  await nextTick()
  const mainEl = document.querySelector('.el-main.main-with-header')
  if (mainEl && !backgroundImageUrl.value) {
    mainEl.style.background = '#f5f7fa'
  }
})

onUnmounted(() => {
  const mainEl = document.querySelector('.el-main.main-with-header')
  if (mainEl) {
    mainEl.style.background = '#f5f7fa'
  }
})

const handleScenicChange = (id) => {
  if (!id) return
  localStorage.setItem('current_scenic_spot_id', String(id))
  selectedScenic.value = scenicSpots.value.find((s) => s.id === id) || null
}

const navigateIfSelected = (path) => {
  if (!selectedScenicId.value) {
    ElMessage.error('请先选择您所在的景区')
    return
  }
  router.push(path)
}
</script>

<style scoped>
.home {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 20px;
  position: relative;
  background: #f5f7fa;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.home.has-background {
  background: transparent;
}

.home.has-background::before {
  content: '';
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: var(--bg-image);
  background-size: cover;
  background-position: center center;
  background-repeat: no-repeat;
  z-index: 0;
  pointer-events: none;
  transition: opacity 0.25s ease;
}
@media (prefers-reduced-motion: reduce) {
  .home.has-background::before { transition: none; }
}

.home-card {
  max-width: 900px;
  margin: 0 auto;
  position: relative;
  z-index: 10;
  background: #ffffff !important;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  border-radius: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.scenic-select-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}

.feature-cards {
  align-items: stretch;
}

.feature-cards .feature-col {
  display: flex;
}

.feature-cards .feature-col .el-card {
  width: 100%;
  flex: 1;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  transition: transform 0.12s ease;
}
.feature-cards .feature-col .el-card:not(.disabled):hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.1);
}
@media (prefers-reduced-motion: reduce) {
  .feature-cards .feature-col .el-card { transition: none; }
  .feature-cards .feature-col .el-card:not(.disabled):hover { transform: none; }
}

.feature-cards .feature-col .el-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: center;
  padding-top: 24px;
}

.el-card {
  text-align: center;
  cursor: pointer;
  background: #ffffff !important;
}


.el-icon {
  color: #409eff;
  margin-bottom: 10px;
}
</style>

