<template>
  <div class="live2d-wrap">
    <canvas id="live2dCanvas" ref="canvasRef" class="live2d-canvas"></canvas>
    <div v-if="characterLoading" class="live2d-loading">
      <span>加载中…</span>
    </div>
    <div v-if="contextLost" class="live2d-lost">
      <span>画面恢复中…</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { LAppDelegate } from '../lib/live2d/src/lappdelegate'
import { Live2dManager } from '../lib/live2d/live2dManager'
import { RESOURCE_TYPE } from '../lib/adhProtocol'

const props = defineProps({
  characterName: { type: String, default: 'Mao' },
  characterGroup: { type: String, default: 'free' },
})

const canvasRef = ref(null)
const characterLoading = ref(false)
const contextLost = ref(false)
let resizeHandler = null
let contextLostHandler = null
let contextRestoredHandler = null

const buildCharacterResource = () => {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const base = `${origin}/sentio/characters/${props.characterGroup}/${props.characterName}/`
  return {
    resource_id: `${props.characterGroup}:${props.characterName}`,
    name: props.characterName,
    type: RESOURCE_TYPE.CHARACTER,
    link: `${base}${props.characterName}.model3.json`,
  }
}

const loadCharacter = () => {
  try {
    characterLoading.value = true
    Live2dManager.getInstance().changeCharacter(buildCharacterResource())
    // 等待模型就绪（轮询 isReady，最多 5s）
    const start = Date.now()
    const waitReady = () => {
      if (Live2dManager.getInstance().isReady()) {
        characterLoading.value = false
        return
      }
      if (Date.now() - start > 5000) {
        characterLoading.value = false
        return
      }
      setTimeout(waitReady, 100)
    }
    Live2dManager.getInstance().setReady(true)
    waitReady()
  } catch (e) {
    console.error('数字人角色加载失败:', e)
    characterLoading.value = false
  }
}

function ensureLive2DCore() {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined' && window.Live2DCubismCore) {
      resolve()
      return
    }
    const origin = window.location.origin
    const src = `${origin}/sentio/core/live2dcubismcore.min.js`
    const existing = document.querySelector('script[src*="live2dcubismcore.min.js"]')
    if (existing) {
      const done = () => resolve()
      if (window.Live2DCubismCore) {
        done()
        return
      }
      existing.addEventListener('load', done)
      setTimeout(() => {
        if (window.Live2DCubismCore) done()
      }, 50)
      return
    }
    const script = document.createElement('script')
    script.src = src
    script.onload = () => resolve()
    script.onerror = () => resolve()
    document.head.appendChild(script)
  })
}

let initDone = false
let resizeObserver = null

const isMobileDevice = () => /iPhone|iPad|Android|Mobile/i.test(navigator.userAgent)

function applyDPR(canvas) {
  // 按设备像素比设置 canvas 物理尺寸，避免高分屏（Retina/AMOLED）模糊
  const dpr = Math.min(window.devicePixelRatio || 1, 2) // 超过 2x 收益递减
  const w = canvas.clientWidth || canvas.offsetWidth || 0
  const h = canvas.clientHeight || canvas.offsetHeight || 0
  if (w > 0 && h > 0) {
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
  }
}

function doInit() {
  const canvas = canvasRef.value
  if (!canvas || initDone) return
  const w = canvas.clientWidth || canvas.offsetWidth || 0
  const h = canvas.clientHeight || canvas.offsetHeight || 0
  if (w < 10 || h < 10) return
  initDone = true
  applyDPR(canvas)
  if (resizeObserver && canvasRef.value) {
    try { resizeObserver.unobserve(canvasRef.value) } catch (_) {}
    resizeObserver = null
  }
  const ok = LAppDelegate.getInstance().initialize()
  if (!ok) {
    initDone = false
    return
  }
  LAppDelegate.getInstance().run()
  loadCharacter()
  resizeHandler = () => {
    if (canvasRef.value) applyDPR(canvasRef.value)
    LAppDelegate.getInstance().onResize()
  }
  window.addEventListener('resize', resizeHandler, { passive: true })

  // WebGL 上下文丢失/恢复处理（切后台、GPU 重置等场景）
  contextLostHandler = (e) => {
    e.preventDefault()
    contextLost.value = true
    console.warn('[Live2DCanvas] WebGL context lost')
  }
  contextRestoredHandler = () => {
    contextLost.value = false
    initDone = false
    console.info('[Live2DCanvas] WebGL context restored, reinitializing...')
    doInit()
  }
  canvas.addEventListener('webglcontextlost', contextLostHandler)
  canvas.addEventListener('webglcontextrestored', contextRestoredHandler)
}

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  ensureLive2DCore().then(() => {
    const w = canvas.clientWidth || canvas.offsetWidth || 0
    const h = canvas.clientHeight || canvas.offsetHeight || 0
    if (w >= 10 && h >= 10) {
      doInit()
      return
    }
    resizeObserver = new ResizeObserver(() => {
      const c = canvasRef.value
      if (!c || initDone) return
      const w2 = c.clientWidth || c.offsetWidth || 0
      const h2 = c.clientHeight || c.offsetHeight || 0
      if (w2 >= 10 && h2 >= 10) doInit()
    })
    resizeObserver.observe(canvas)
    // 移动端布局稳定更快，缩短超时（桌面 800ms / 移动 400ms）
    setTimeout(() => {
      if (initDone) return
      const w2 = canvas.clientWidth || canvas.offsetWidth || 0
      const h2 = canvas.clientHeight || canvas.offsetHeight || 0
      if (w2 >= 10 && h2 >= 10) doInit()
    }, isMobileDevice() ? 400 : 800)
  })
})

watch(
  () => [props.characterName, props.characterGroup],
  () => {
    if (!canvasRef.value) return
    loadCharacter()
  }
)

onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  if (resizeObserver && canvasRef.value) {
    try { resizeObserver.unobserve(canvasRef.value) } catch (_) {}
    resizeObserver = null
  }
  const c = canvasRef.value
  if (c) {
    if (contextLostHandler) c.removeEventListener('webglcontextlost', contextLostHandler)
    if (contextRestoredHandler) c.removeEventListener('webglcontextrestored', contextRestoredHandler)
  }
  LAppDelegate.releaseInstance()
})
</script>

<style scoped>
.live2d-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 300px;
  background: #0b0f18;
  border-radius: 12px;
  overflow: hidden;
}

.live2d-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.live2d-loading,
.live2d-lost {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(11, 15, 24, 0.7);
  color: #aaa;
  font-size: 14px;
  pointer-events: none;
  border-radius: 12px;
}
</style>


