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
          class="scenic-select"
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
        <el-col :xs="24" :sm="24" :md="8" class="feature-col">
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
        <el-col :xs="24" :sm="24" :md="8" class="feature-col">
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
        <el-col :xs="24" :sm="24" :md="8" class="feature-col">
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

// 图片地址：扫码/隧道访问时用相对路径走同源，由 Vite 代理 /uploads 到后端
const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || 'http://localhost:18000'
const getImageUrl = (url) => {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  if (url.startsWith('/')) return url
  return `${backendOrigin}${url}`
}
const backgroundImageUrl = computed(() => getImageUrl(selectedScenic.value?.cover_image_url))

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
  // 景区列表不阻塞首屏渲染，请求在后台完成
  api.get('/attractions/scenic-spots').then(res => {
    scenicSpots.value = res.data || []
  }).catch(e => {
    console.error('加载景区列表失败:', e)
  })
  await nextTick()
  const mainEl = document.querySelector('.el-main.main-with-header')
  if (mainEl && !backgroundImageUrl.value) {
    mainEl.style.background = '#f5f7fa'
  }
  // 空闲时预取语音导览页，点击时响应更快
  if (typeof requestIdleCallback !== 'undefined') {
    requestIdleCallback(() => {
      import(/* webpackChunkName: "voice-guide" */ './VoiceGuide.vue').catch(() => {})
    }, { timeout: 2000 })
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
.scenic-select-wrapper :deep(.el-select) {
  width: 100%;
  max-width: 320px;
}
@media (max-width: 768px) {
  .home {
    padding: 16px !important;
    justify-content: center !important;
    align-items: center !important;
  }
  .home-card {
    width: calc(100% - 48px) !important; /* 左右各留 24px，更像中间一块小区域 */
    max-width: 320px !important; /* 控制在语音导览板块大小 */
    max-height: 52vh !important; /* 约半屏高，突出“一块区域” */
    margin: 0 auto !important;
    /* 白色更透明，背景图更明显 */
    background: rgba(255, 255, 255, 0.48) !important;
    backdrop-filter: blur(6px) !important;
    -webkit-backdrop-filter: blur(6px) !important;
    display: flex !important;
    flex-direction: column !important;
    overflow: hidden !important;
    padding: 0 !important;
    border-radius: 14px !important;
  }
  .home-card :deep(.el-card__header) {
    padding: 10px 12px !important;
    flex-shrink: 0;
  }
  .home-card :deep(.el-card__body) {
    padding: 8px 12px 12px !important;
    overflow-y: auto !important;
    -webkit-overflow-scrolling: touch !important;
    flex: 1 !important;
    min-height: 0 !important;
  }
  .feature-cards {
    margin-top: 12px !important;
    gap: 0 12px;
  }
  .feature-cards .feature-col .el-card {
    background: rgba(255, 255, 255, 0.55) !important;
    backdrop-filter: blur(5px) !important;
    -webkit-backdrop-filter: blur(5px) !important;
  }
  .feature-cards .feature-col .el-card :deep(.el-card__body) {
    padding-top: 14px !important;
  }
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

