<template>
  <div class="digital-avatar-container">
    <div ref="avatarContainer" class="avatar-view"></div>
    <div v-if="!isReady" class="loading-overlay">
      <el-icon class="is-loading"><Loading /></el-icon>
      <p>数字人加载中...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'

const props = defineProps({
  // 阿里云数字人配置
  accessKeyId: {
    type: String,
    required: true
  },
  accessKeySecret: {
    type: String,
    required: true
  },
  appId: {
    type: String,
    required: true
  },
  avatarId: {
    type: String,
    default: 'default'
  },
  // 是否自动播放
  autoPlay: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['ready', 'error', 'speaking', 'stopped'])

const avatarContainer = ref(null)
const isReady = ref(false)
let avatarInstance = null

// 初始化数字人
const initAvatar = async () => {
  if (!window.AvatarSDK) {
    console.error('阿里云数字人 SDK 未加载')
    emit('error', 'SDK未加载')
    return
  }

  try {
    // 创建数字人实例
    avatarInstance = new window.AvatarSDK({
      container: avatarContainer.value,
      accessKeyId: props.accessKeyId,
      accessKeySecret: props.accessKeySecret,
      appId: props.appId,
      avatarId: props.avatarId,
      onReady: () => {
        console.log('数字人初始化成功')
        isReady.value = true
        emit('ready')
      },
      onError: (error) => {
        console.error('数字人初始化失败:', error)
        emit('error', error)
      },
      onSpeaking: () => {
        emit('speaking')
      },
      onStopped: () => {
        emit('stopped')
      }
    })

    await avatarInstance.init()
  } catch (error) {
    console.error('数字人初始化异常:', error)
    emit('error', error)
  }
}

// 播放文本
const speak = async (text) => {
  if (!avatarInstance || !isReady.value) {
    console.warn('数字人未就绪')
    return
  }

  try {
    await avatarInstance.speak(text)
  } catch (error) {
    console.error('播放失败:', error)
    emit('error', error)
  }
}

// 停止播放
const stop = () => {
  if (avatarInstance && isReady.value) {
    avatarInstance.stop()
  }
}

// 设置表情
const setExpression = (expression) => {
  if (avatarInstance && isReady.value) {
    avatarInstance.setExpression(expression)
  }
}

// 设置动作
const setAction = (action) => {
  if (avatarInstance && isReady.value) {
    avatarInstance.setAction(action)
  }
}

// 销毁实例
const destroy = () => {
  if (avatarInstance) {
    avatarInstance.destroy()
    avatarInstance = null
    isReady.value = false
  }
}

// 监听 avatarId 变化
watch(() => props.avatarId, () => {
  if (avatarInstance) {
    destroy()
    initAvatar()
  }
})

onMounted(() => {
  initAvatar()
})

onUnmounted(() => {
  destroy()
})

// 暴露方法供父组件调用
defineExpose({
  speak,
  stop,
  setExpression,
  setAction,
  isReady
})
</script>

<style scoped>
.digital-avatar-container {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 400px;
  background: #f5f7fa;
  border-radius: 8px;
  overflow: hidden;
}

.avatar-view {
  width: 100%;
  height: 100%;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.9);
  z-index: 10;
}

.loading-overlay p {
  margin-top: 10px;
  color: #666;
}
</style>

