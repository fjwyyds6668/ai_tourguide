<template>
  <div class="live2d-wrap">
    <canvas id="live2dCanvas" ref="canvasRef" class="live2d-canvas"></canvas>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { LAppDelegate } from '../lib/live2d/src/lappdelegate'
import { Live2dManager } from '../lib/live2d/live2dManager'
import { RESOURCE_TYPE } from '../lib/adhProtocol'

const props = defineProps({
  // 角色目录名（对应 /public/sentio/characters/free/<Name>/）
  characterName: { type: String, default: 'Mao' },
  // 模型目录（默认 free）
  characterGroup: { type: String, default: 'free' },
})

const canvasRef = ref(null)
let resizeHandler = null

const buildCharacterResource = () => {
  const base = `/sentio/characters/${props.characterGroup}/${props.characterName}/`
  return {
    resource_id: `${props.characterGroup}:${props.characterName}`,
    name: props.characterName,
    type: RESOURCE_TYPE.CHARACTER,
    link: `${base}${props.characterName}.model3.json`,
  }
}

onMounted(() => {
  // 初始化 Live2D（依赖 canvas id=live2dCanvas）
  const ok = LAppDelegate.getInstance().initialize()
  if (!ok) return

  // 运行渲染循环
  LAppDelegate.getInstance().run()

  // 加载默认角色
  try {
    Live2dManager.getInstance().changeCharacter(buildCharacterResource())
    Live2dManager.getInstance().setReady(true)
  } catch (e) {
    console.error('Live2D load character failed:', e)
  }

  resizeHandler = () => LAppDelegate.getInstance().onResize()
  window.addEventListener('resize', resizeHandler, { passive: true })
})

onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  LAppDelegate.releaseInstance()
})
</script>

<style scoped>
.live2d-wrap {
  width: 100%;
  height: 70vh;
  min-height: 520px;
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


