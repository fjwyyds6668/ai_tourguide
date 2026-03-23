<template>
  <div class="map-page">
    <el-card class="map-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">景区地图</span>
          <div class="header-actions">
            <el-button size="small" @click="resetView">还原</el-button>
          </div>
        </div>
      </template>

      <div
        class="map-container"
        ref="containerRef"
        @wheel.prevent="onWheel"
        @mousedown="onMouseDown"
        @mousemove="onMouseMove"
        @mouseup="onMouseUp"
        @mouseleave="onMouseUp"
        @touchstart.prevent="onTouchStart"
        @touchmove.prevent="onTouchMove"
        @touchend="onTouchEnd"
      >
        <img
          ref="imgRef"
          :src="mapUrl"
          class="map-img"
          :style="imgStyle"
          alt="景区地图"
          draggable="false"
          @load="onImageLoad"
          @error="onImageError"
        />
        <div v-if="error" class="map-error">
          <el-icon :size="48"><PictureFilled /></el-icon>
          <p>地图加载失败</p>
        </div>
      </div>

      <div class="zoom-bar">
        <el-button :icon="Minus" circle size="small" @click="zoomOut" />
        <span class="zoom-label">{{ Math.round(scale * 100) }}%</span>
        <el-button :icon="Plus" circle size="small" @click="zoomIn" />
      </div>

      <p class="map-tip">滚轮缩放 · 拖拽移动</p>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Plus, Minus, PictureFilled } from '@element-plus/icons-vue'

const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || 'http://localhost:18000'
const mapUrl = `${backendOrigin}/uploads/images/map.jpg`

const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const error = ref(false)
const containerRef = ref(null)
const imgRef = ref(null)

const MIN_SCALE = 0.3
const MAX_SCALE = 5

const imgStyle = computed(() => ({
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
  cursor: isDragging.value ? 'grabbing' : 'grab',
}))

// 图片加载后适应容器宽度
function onImageLoad() {
  error.value = false
}
function onImageError() {
  error.value = true
}

function resetView() {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
}

function zoomAt(delta, cx, cy) {
  const container = containerRef.value
  if (!container) return
  const rect = container.getBoundingClientRect()
  const ox = cx - rect.left - rect.width / 2
  const oy = cy - rect.top - rect.height / 2
  const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value * delta))
  const ratio = newScale / scale.value
  translateX.value = ox + (translateX.value - ox) * ratio
  translateY.value = oy + (translateY.value - oy) * ratio
  scale.value = newScale
}

function zoomIn() {
  const container = containerRef.value
  if (!container) return
  const rect = container.getBoundingClientRect()
  zoomAt(1.2, rect.left + rect.width / 2, rect.top + rect.height / 2)
}
function zoomOut() {
  const container = containerRef.value
  if (!container) return
  const rect = container.getBoundingClientRect()
  zoomAt(1 / 1.2, rect.left + rect.width / 2, rect.top + rect.height / 2)
}

// 鼠标滚轮缩放
function onWheel(e) {
  const delta = e.deltaY < 0 ? 1.15 : 1 / 1.15
  zoomAt(delta, e.clientX, e.clientY)
}

// 鼠标拖拽
const isDragging = ref(false)
let lastX = 0, lastY = 0
function onMouseDown(e) {
  if (e.button !== 0) return
  isDragging.value = true
  lastX = e.clientX
  lastY = e.clientY
}
function onMouseMove(e) {
  if (!isDragging.value) return
  translateX.value += e.clientX - lastX
  translateY.value += e.clientY - lastY
  lastX = e.clientX
  lastY = e.clientY
}
function onMouseUp() {
  isDragging.value = false
}

// 触摸拖拽 + 双指缩放
let lastTouches = null
function onTouchStart(e) {
  lastTouches = e.touches
}
function onTouchMove(e) {
  if (!lastTouches) return
  if (e.touches.length === 1 && lastTouches.length === 1) {
    translateX.value += e.touches[0].clientX - lastTouches[0].clientX
    translateY.value += e.touches[0].clientY - lastTouches[0].clientY
  } else if (e.touches.length === 2 && lastTouches.length === 2) {
    const prevDist = Math.hypot(
      lastTouches[0].clientX - lastTouches[1].clientX,
      lastTouches[0].clientY - lastTouches[1].clientY
    )
    const currDist = Math.hypot(
      e.touches[0].clientX - e.touches[1].clientX,
      e.touches[0].clientY - e.touches[1].clientY
    )
    if (prevDist > 0) {
      const cx = (e.touches[0].clientX + e.touches[1].clientX) / 2
      const cy = (e.touches[0].clientY + e.touches[1].clientY) / 2
      zoomAt(currDist / prevDist, cx, cy)
    }
  }
  lastTouches = e.touches
}
function onTouchEnd() {
  lastTouches = null
}
</script>

<style scoped>
.map-page {
  width: 100%;
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}

.map-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.map-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.map-container {
  flex: 1;
  overflow: hidden;
  border-radius: 8px;
  background: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  min-height: 300px;
  user-select: none;
}

.map-img {
  max-width: 100%;
  max-height: 100%;
  transform-origin: center center;
  transition: transform 0.05s;
  pointer-events: none;
}

.map-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #909399;
  gap: 8px;
}

.zoom-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 0 4px;
}

.zoom-label {
  font-size: 13px;
  color: #606266;
  min-width: 48px;
  text-align: center;
}

.map-tip {
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
  margin: 0;
}
</style>
