<template>
  <div class="live2d-wrap">
    <canvas id="live2dCanvas" ref="canvasRef" class="live2d-canvas"></canvas>
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
let resizeHandler = null

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
    Live2dManager.getInstance().changeCharacter(buildCharacterResource())
    Live2dManager.getInstance().setReady(true)
  } catch (e) {
    console.error('数字人角色加载失败:', e)
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

function doInit() {
  const canvas = canvasRef.value
  if (!canvas || initDone) return
  const w = canvas.clientWidth || canvas.offsetWidth || 0
  const h = canvas.clientHeight || canvas.offsetHeight || 0
  if (w < 10 || h < 10) return
  initDone = true
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
  resizeHandler = () => LAppDelegate.getInstance().onResize()
  window.addEventListener('resize', resizeHandler, { passive: true })
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
    setTimeout(() => {
      if (initDone) return
      const w2 = canvas.clientWidth || canvas.offsetWidth || 0
      const h2 = canvas.clientHeight || canvas.offsetHeight || 0
      if (w2 >= 10 && h2 >= 10) doInit()
    }, 800)
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
  LAppDelegate.releaseInstance()
})
</script>

<style scoped>
.live2d-wrap {
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
</style>


