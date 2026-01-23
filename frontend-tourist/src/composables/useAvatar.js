/**
 * 数字人 Avatar Hook
 * 封装阿里云数字人 SDK 的使用
 */
import { ref, onUnmounted } from 'vue'

export function useAvatar(config) {
  const isReady = ref(false)
  const isSpeaking = ref(false)
  let avatarInstance = null

  const init = async () => {
    if (!window.AvatarSDK) {
      throw new Error('阿里云数字人 SDK 未加载，请检查 CDN 引入')
    }

    try {
      avatarInstance = new window.AvatarSDK({
        ...config,
        onReady: () => {
          isReady.value = true
          config.onReady?.()
        },
        onError: (error) => {
          console.error('数字人错误:', error)
          config.onError?.(error)
        },
        onSpeaking: () => {
          isSpeaking.value = true
          config.onSpeaking?.()
        },
        onStopped: () => {
          isSpeaking.value = false
          config.onStopped?.()
        }
      })

      await avatarInstance.init()
      return avatarInstance
    } catch (error) {
      console.error('数字人初始化失败:', error)
      throw error
    }
  }

  const speak = async (text) => {
    if (!avatarInstance || !isReady.value) {
      throw new Error('数字人未就绪')
    }
    await avatarInstance.speak(text)
  }

  const stop = () => {
    if (avatarInstance) {
      avatarInstance.stop()
    }
  }

  const destroy = () => {
    if (avatarInstance) {
      avatarInstance.destroy()
      avatarInstance = null
      isReady.value = false
    }
  }

  onUnmounted(() => {
    destroy()
  })

  return {
    isReady,
    isSpeaking,
    init,
    speak,
    stop,
    destroy
  }
}

