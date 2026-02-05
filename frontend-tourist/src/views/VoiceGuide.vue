<template>
  <div class="voice-guide">
    <!-- 角色选择 -->
    <el-card class="section-card role-card">
      <template #header>
        <span class="card-title">选择数字人角色</span>
      </template>
      <el-radio-group v-model="selectedCharacterId" @change="handleCharacterChange" class="role-group">
        <el-radio-button
          v-for="character in characters"
          :key="character.id"
          :label="character.id"
        >
          {{ character.name }}
        </el-radio-button>
      </el-radio-group>
    </el-card>

    <el-row :gutter="20" class="main-row">
      <!-- 左侧：数字人展示区 -->
      <el-col :xs="24" :sm="24" :md="14" :lg="14">
        <el-card class="section-card avatar-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">数字人导游</span>
            </div>
          </template>
          
          <div class="avatar-wrapper" :style="scenicBackgroundStyle">
            <Live2DCanvas
              :character-name="currentLive2DName"
              :character-group="currentLive2DGroup"
            />
          </div>

          <div class="text-input-area">
            <p class="input-hint">支持语音或文字，与数字人对话</p>
            <div class="textarea-wrapper">
              <el-input
                v-model="textInput"
                type="textarea"
                :rows="3"
                placeholder="在此输入要对数字人说的话（Enter 发送，Ctrl+Enter 换行）"
                @keyup.enter.exact.prevent="handleSendText"
                @keyup.ctrl.enter.prevent="handleSendText"
                class="textarea-input"
              />
              <div class="input-buttons">
                <el-button
                  type="primary"
                  :icon="isRecording ? 'VideoPause' : 'Microphone'"
                  @click="toggleRecording"
                  :loading="processing"
                  circle
                  size="default"
                  :title="isRecording ? '停止录音' : '开始录音'"
                />
                <el-button
                  type="primary"
                  @click="handleSendText"
                  :disabled="!textInput.trim() || processing"
                  size="default"
                >
                  发送
                </el-button>
                <el-button
                  v-if="isSpeaking"
                  @click="stopSpeaking"
                  size="default"
                >
                  停止播报
                </el-button>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：对话记录 -->
      <el-col :xs="24" :sm="24" :md="10" :lg="10">
        <el-card class="section-card chat-card">
          <template #header>
            <span class="card-title">对话记录</span>
          </template>
          
          <div class="conversation-list" ref="conversationListRef">
            <div
              v-for="(msg, index) in conversationHistory"
              :key="`${msg.timestamp}-${index}`"
              :class="['message-item', msg.role]"
            >
              <div class="message-header">
                <strong>{{ msg.role === 'user' ? '您' : 'AI导游' }}</strong>
                <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="message-content">{{ msg.content }}</div>
            </div>
            <div v-if="conversationHistory.length === 0" class="empty-message">
              <el-icon class="empty-icon"><ChatDotRound /></el-icon>
              <p>还没有对话记录</p>
              <p class="empty-desc">在左侧输入或点击麦克风开始与 AI 导游交流</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, ChatDotRound } from '@element-plus/icons-vue'
import Live2DCanvas from '../components/Live2DCanvas.vue'
import api from '../api'
import { formatTime } from '../utils/format'
import { Live2dManager } from '../lib/live2d/live2dManager'
import { LAppDelegate } from '../lib/live2d/src/lappdelegate'

const isRecording = ref(false)
const isSpeaking = ref(false)
const processing = ref(false)
const selectedCharacterId = ref(null)
const sessionId = ref(null)
const characters = ref([])
// 限制对话历史长度，避免内存占用过大和渲染性能问题
const MAX_HISTORY_LENGTH = 50
const conversationHistory = ref([])
const textInput = ref('')

let mediaRecorder = null
let audioChunks = []

const audioQueue = []
let isPlayingQueue = false
let currentAudio = null
let ttsRequestQueue = Promise.resolve()
// 用于“失效”旧的 TTS，会话 ID 每次新回答或停止播报时自增
let ttsSessionId = 0

const currentScenic = ref(null)
const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || 'http://localhost:18000'

// 仅在本页面时禁止整体页面滚动，离开时恢复，保证只有对话区域可滚动
let previousBodyOverflow = ''

onMounted(async () => {
  if (typeof document !== 'undefined') {
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  await loadCharacters()
  if (characters.value.length > 0) {
    selectedCharacterId.value = characters.value[0].id
  }
  try {
    const savedId = localStorage.getItem('current_scenic_spot_id')
    if (!savedId) return
    const idNum = Number(savedId)
    if (Number.isNaN(idNum)) return
    const res = await api.get('/attractions/scenic-spots')
    const spots = res.data || []
    currentScenic.value = spots.find((s) => s.id === idNum) || null
  } catch (e) {
    console.error('加载当前景区信息失败:', e)
  }
})

onUnmounted(() => {
  if (typeof document !== 'undefined') {
    document.body.style.overflow = previousBodyOverflow || ''
  }
})

// 加载角色列表（带重试机制）
const loadCharacters = async (retries = 2) => {
  try {
    const res = await api.get('/characters/characters', {
      params: { active_only: true },
      timeout: 10000
    })
    characters.value = res.data || []
  } catch (error) {
    if (retries > 0) {
      console.warn(`加载角色失败，${retries} 次重试机会...`, error)
      await new Promise(resolve => setTimeout(resolve, 1000))
      return loadCharacters(retries - 1)
    }
    console.error('加载角色失败:', error)
    ElMessage.error('加载角色失败，请刷新页面重试')
  }
}

const currentLive2DName = computed(() => {
  if (!selectedCharacterId.value || !characters.value.length) return 'Mao'
  const c = characters.value.find((ch) => ch.id === selectedCharacterId.value)
  return c?.live2d_character_name || 'Mao'
})
const currentLive2DGroup = computed(() => {
  if (!selectedCharacterId.value || !characters.value.length) return 'free'
  const c = characters.value.find((ch) => ch.id === selectedCharacterId.value)
  return c?.live2d_character_group || 'free'
})

const handleCharacterChange = () => {}

const toggleRecording = async () => {
  if (!isRecording.value) {
    startRecording()
  } else {
    stopRecording()
  }
}

const startRecording = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder = new MediaRecorder(stream)
    audioChunks = []
    
    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data)
    }
    
    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/wav' })
      await processAudio(audioBlob)
      stream.getTracks().forEach(track => track.stop())
    }
    
    mediaRecorder.start()
    isRecording.value = true
  } catch (error) {
    ElMessage.error('无法访问麦克风')
    console.error(error)
  }
}

const stopRecording = () => {
  if (mediaRecorder && isRecording.value) {
    mediaRecorder.stop()
    isRecording.value = false
  }
}

const processAudio = async (audioBlob) => {
  processing.value = true
  try {
    const formData = new FormData()
    formData.append('file', audioBlob, 'audio.wav')
    formData.append('method', 'whisper')
    
    const transcribeRes = await api.post('/voice/transcribe', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    const queryText = transcribeRes.data.text
    
    addMessage('user', queryText)
    scrollToBottom()
    
    initAudioAnalyzer().catch(() => {})
    
    const generateRes = await api.post('/rag/generate', {
      query: queryText,
      session_id: sessionId.value,
      character_id: selectedCharacterId.value,
      use_rag: true
    })
    
    const answer = generateRes.data?.answer || generateRes.data || ''
    sessionId.value = generateRes.data?.session_id || sessionId.value
    
    if (!answer || answer.trim() === '') {
      ElMessage.warning('AI 未返回有效回答，请重试')
      return
    }
    
    addAssistantStreamMessage(answer, selectedCharacterId.value)
    scrollToBottom()
  } catch (error) {
    const msg = await extractErrorMessage(error)
    ElMessage.error('处理失败：' + msg)
    console.error('processAudio error:', error)
  } finally {
    processing.value = false
  }
}

const handleSendText = async () => {
  const queryText = textInput.value.trim()
  if (!queryText) {
    ElMessage.warning('请输入要对数字人说的话')
    return
  }

  if (processing.value) {
    ElMessage.warning('正在处理中，请稍候...')
    return
  }

  processing.value = true
  textInput.value = ''
  try {
    addMessage('user', queryText)
    scrollToBottom()

    Promise.all([
      Promise.resolve(triggerSpeakingMotion()),
      initAudioAnalyzer()
    ]).catch(() => {})

    const generateRes = await api.post('/rag/generate', {
      query: queryText,
      session_id: sessionId.value,
      character_id: selectedCharacterId.value,
      use_rag: true
    })

    const answer = generateRes.data?.answer || generateRes.data || ''
    sessionId.value = generateRes.data?.session_id || sessionId.value
    
    if (!answer || answer.trim() === '') {
      ElMessage.warning('AI 未返回有效回答，请重试')
      return
    }

    addAssistantStreamMessage(answer, selectedCharacterId.value)
    scrollToBottom()
  } catch (error) {
    const msg = await extractErrorMessage(error)
    ElMessage.error('处理失败：' + msg)
    console.error('handleSendText error:', error)
  } finally {
    processing.value = false
  }
}

const extractErrorMessage = async (error) => {
  try {
    const anyErr = error
    const resp = anyErr?.response
    if (resp?.data instanceof Blob) {
      const text = await resp.data.text()
      try {
        const json = JSON.parse(text)
        return json.detail || text
      } catch {
        return text || anyErr.message || '未知错误'
      }
    }
    return resp?.data?.detail || anyErr.message || '未知错误'
  } catch (e) {
    console.error('extractErrorMessage failed:', e)
    return error?.message || '未知错误'
  }
}

const stopSpeaking = () => {
  if (currentAudio) {
    currentAudio.pause()
    currentAudio = null
  }
  if (audioSource) {
    audioSource.stop()
    audioSource.disconnect()
    audioSource = null
  }
  audioQueue.forEach(url => URL.revokeObjectURL(url))
  audioQueue.length = 0
  isPlayingQueue = false
  isSpeaking.value = false
  // 使当前及之前回答的 TTS 全部失效，避免新对话继续播旧内容
  ttsSessionId += 1
  
  try {
    const manager = Live2dManager.getInstance()
    if (manager) {
      manager.setLipFactor(0)
    }
  } catch (e) {
  }
}

const scenicBackgroundStyle = computed(() => {
  const url = currentScenic.value?.cover_image_url
  if (!url) {
    return {}
  }
  const full =
    url.startsWith('http://') || url.startsWith('https://')
      ? url
      : `${backendOrigin}${url}`
  return {
    backgroundImage: `url(${full})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center center',
    backgroundRepeat: 'no-repeat',
  }
})

const addMessage = (role, content) => {
  conversationHistory.value.push({
    role,
    content,
    timestamp: new Date().toISOString()
  })
  if (conversationHistory.value.length > MAX_HISTORY_LENGTH) {
    conversationHistory.value = conversationHistory.value.slice(-MAX_HISTORY_LENGTH)
  }
}

let audioContext = null
let analyser = null
let audioSource = null

const initAudioAnalyzer = async () => {
  if (!audioContext) {
    try {
      audioContext = new (window.AudioContext || window.webkitAudioContext)()
      analyser = audioContext.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.8
      if (audioContext.state === 'suspended') {
        await audioContext.resume()
      }
    } catch (e) {
      console.warn('音频上下文初始化失败:', e)
      throw e
    }
  }
}

const updateLipSync = () => {
  if (!analyser || !isSpeaking.value) {
    return
  }
  
  const dataArray = new Uint8Array(analyser.frequencyBinCount)
  analyser.getByteFrequencyData(dataArray)
  
  let sum = 0
  for (let i = 0; i < dataArray.length; i++) {
    sum += dataArray[i] * dataArray[i]
  }
  const rms = Math.sqrt(sum / dataArray.length) / 255
  
  try {
    const manager = Live2dManager.getInstance()
    if (manager && manager.isReady()) {
      manager.setLipFactor(Math.min(rms * 2, 1.0))
    }
  } catch (e) {
  }
  
  if (isSpeaking.value) {
    requestAnimationFrame(updateLipSync)
  }
}

const playAudioQueue = async () => {
  if (isPlayingQueue || audioQueue.length === 0) {
    return
  }

  isPlayingQueue = true
  isSpeaking.value = true
  
  initAudioAnalyzer()

  while (audioQueue.length > 0) {
    const audioUrl = audioQueue.shift()
    const isLastChunk = audioQueue.length === 0
    try {
      await new Promise((resolve, reject) => {
        fetch(audioUrl)
          .then(response => response.arrayBuffer())
          .then(arrayBuffer => {
            audioContext.decodeAudioData(arrayBuffer)
              .then(audioBuffer => {
                if (audioSource) {
                  audioSource.disconnect()
                }
                audioSource = audioContext.createBufferSource()
                audioSource.buffer = audioBuffer
                
                audioSource.connect(analyser)
                analyser.connect(audioContext.destination)
                
                audioSource.start(0)
                updateLipSync()
                
                const timeout = setTimeout(() => {
                  console.warn('音频播放超时，强制结束，是否最后一段:', isLastChunk)
                  if (audioSource) {
                    try {
                      audioSource.stop()
                    } catch (e) {
                    }
                  }
                  URL.revokeObjectURL(audioUrl)
                  resolve()
                }, audioBuffer.duration * 1000 + 2000)
                
                audioSource.onended = () => {
                  clearTimeout(timeout)
                  URL.revokeObjectURL(audioUrl)
                  if (isLastChunk) {
                    console.log('最后一段音频播放完成，等待额外延迟确保完整')
                    setTimeout(() => {
                      resolve()
                    }, 300)
                  } else {
                    resolve()
                  }
                }
                
                currentAudio = {
                  pause: () => {
                    clearTimeout(timeout)
                    if (audioSource) {
                      audioSource.stop()
                      audioSource.disconnect()
                      audioSource = null
                    }
                  }
                }
              })
              .catch(reject)
          })
          .catch(reject)
      })
    } catch (error) {
      console.error('播放音频失败:', error)
      try {
        await new Promise((resolve, reject) => {
          currentAudio = new Audio(audioUrl)
          currentAudio.onended = () => {
            URL.revokeObjectURL(audioUrl)
            resolve()
          }
          currentAudio.onerror = (e) => {
            URL.revokeObjectURL(audioUrl)
            reject(e)
          }
          currentAudio.play().catch(reject)
        })
      } catch (fallbackError) {
        console.error('回退播放也失败:', fallbackError)
      }
    }
  }

  currentAudio = null
  audioSource = null
  isPlayingQueue = false
  isSpeaking.value = false
}

const synthesizeAndQueue = async (text, characterId, sessionId) => {
  if (!text || typeof text !== 'string' || text.length === 0) {
    console.warn('TTS 合成跳过：文本为空或无效', text)
    return
  }

  const cleanedText = text.replace(/\s+/g, ' ').trim()
  if (cleanedText.length === 0) {
    console.warn('TTS 合成跳过：清理后文本为空')
    return
  }

  ttsRequestQueue = ttsRequestQueue.then(async () => {
    // 如果在真正发请求前 session 已经变化，直接跳过
    if (sessionId !== ttsSessionId) {
      return
    }
    try {
      console.log('开始 TTS 合成，文本长度:', cleanedText.length, '预览:', cleanedText.substring(0, 30))
      const synthesizeRes = await api.post(
        '/voice/synthesize',
        { 
          text: cleanedText, 
          character_id: characterId 
        },
        { responseType: 'blob', timeout: 30000 }
      )
      // 请求返回时再次检查，会话是否已经失效（例如用户点了“停止播报”或者开始新对话）
      if (sessionId !== ttsSessionId) {
        console.warn('TTS 结果已过期，丢弃本次音频')
        return
      }

      if (!synthesizeRes.data || synthesizeRes.data.size === 0) {
        console.warn('TTS 返回空音频数据，文本:', cleanedText.substring(0, 50))
        return
      }
      console.log('TTS 合成成功，音频大小:', synthesizeRes.data.size, '字节')
      const audioUrl = URL.createObjectURL(synthesizeRes.data)
      audioQueue.push(audioUrl)
      playAudioQueue()
    } catch (error) {
      console.error('TTS 合成失败:', error, '文本:', cleanedText.substring(0, 50))
      ElMessage.error('语音合成失败，请检查网络连接')
    }
  }).catch(error => {
    console.error('TTS 队列执行失败:', error)
  })
}

// “流式打字 + 分段提前合成”方式：
// 目标：尽量快地让语音开始播放，同时每一段尽量长一些，减少“断句感”
const addAssistantStreamMessage = (fullText, characterId = null) => {
  // 为当前回答创建一个独立的 TTS 会话 ID，用于废弃旧的音频
  const thisTtsSessionId = ++ttsSessionId

  const index = conversationHistory.value.length
  conversationHistory.value.push({
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString()
  })

  if (!fullText) {
    return
  }

  const textLength = fullText.length
  let i = 0
  const interval = 10
  // 每段送给 TTS 的文本长度（比原来的 25 大很多，减少停顿次数）
  const TTS_CHUNK_SIZE = 80
  // 提前量：当“打字位置”离上一段 TTS 文本结尾不足这么多字符时，就开始合成下一段
  const TTS_AHEAD_THRESHOLD = 20
  let ttsSynthesizedLength = 0

  // 重置队列，保证本轮回答的 TTS 顺序播放
  ttsRequestQueue = Promise.resolve()

  // 先用首段文本触发第一次 TTS，让语音尽快开始
  const initialChunkEnd = Math.min(TTS_CHUNK_SIZE, textLength)
  const initialText = fullText.substring(0, initialChunkEnd)
  if (initialText.trim()) {
    synthesizeAndQueue(initialText, characterId || selectedCharacterId.value, thisTtsSessionId)
    ttsSynthesizedLength = initialChunkEnd
  }

  // 打字机效果：逐步把完整回答打印出来
  const timer = setInterval(() => {
    if (i >= textLength) {
      clearInterval(timer)
      return
    }
    const msg = conversationHistory.value[index]
    if (!msg) {
      clearInterval(timer)
      return
    }

    const chunkSize = Math.min(3, textLength - i)
    msg.content += fullText.substring(i, i + chunkSize)
    i += chunkSize

    // 根据“打字进度”提前触发下一段 TTS，减少下一句开头的空白
    if (i >= ttsSynthesizedLength - TTS_AHEAD_THRESHOLD && ttsSynthesizedLength < textLength) {
      const nextChunkStart = ttsSynthesizedLength
      const nextChunkEnd = Math.min(ttsSynthesizedLength + TTS_CHUNK_SIZE, textLength)
      let nextChunk = fullText.substring(nextChunkStart, nextChunkEnd)
      if (nextChunk.trim().length === 0) {
        return
      }

      // 如果是最后一段但结尾没有句号/问号/感叹号，自动补一个，让 TTS 更自然收尾
      if (nextChunkEnd === textLength) {
        const lastChar = nextChunk[nextChunk.length - 1]
        if (!['。', '！', '？', '.', '!', '?'].includes(lastChar)) {
          nextChunk = nextChunk + '。'
        }
      }

      synthesizeAndQueue(nextChunk, characterId || selectedCharacterId.value, thisTtsSessionId)
      ttsSynthesizedLength = nextChunkEnd
    }
  }, interval)
}

const scrollToBottom = () => {
  requestAnimationFrame(() => {
    const listRef = document.querySelector('.conversation-list')
    if (listRef) {
      listRef.scrollTop = listRef.scrollHeight
    }
  })
}

const triggerSpeakingMotion = () => {
  try {
    const delegate = LAppDelegate.getInstance()
    if (!delegate) return
    
    const subdelegates = delegate._subdelegates
    if (!subdelegates || subdelegates.getSize() === 0) return
    
    const subdelegate = subdelegates.at(0)
    const live2dManager = subdelegate?._live2dManager
    if (!live2dManager) return
    
    const models = live2dManager._models
    if (!models || models.getSize() === 0) return
    
    const model = models.at(0)
    if (!model) return
    
    const motionGroup = 'TapBody'
    const modelSetting = model._modelSetting
    if (modelSetting) {
      const motionCount = modelSetting.getMotionCount(motionGroup) || 0
      if (motionCount > 0) {
        const motionNo = Math.floor(Math.random() * motionCount)
        model.startMotion(motionGroup, motionNo, 2)
      }
      
      const expressionCount = modelSetting.getExpressionCount() || 0
      if (expressionCount > 0) {
        let smileIndex = -1
        for (let i = 0; i < expressionCount; i++) {
          const exprName = modelSetting.getExpressionName(i)
          if (exprName === 'smile' || exprName === '微笑' || exprName === 'happy' || exprName === '开心') {
            smileIndex = i
            break
          }
        }
        if (smileIndex >= 0) {
          model.setExpression(modelSetting.getExpressionName(smileIndex))
        }
      }
    }
  } catch (e) {
    console.warn('触发动作失败:', e)
  }
}
</script>

<style scoped>
.voice-guide {
  max-width: 1400px;
  margin: 0 auto;
  padding: 12px;
  /* 占满一屏高度，避免页面整体滚动 */
  height: calc(100vh - 24px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-card {
  margin-bottom: 12px;
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-card :deep(.el-card__header) {
  padding: 10px 16px;
  font-weight: 600;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.section-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px;
}

.card-title {
  font-size: 15px;
  color: #303133;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.history-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.role-card {
  margin-bottom: 12px;
  flex-shrink: 0;
}

.role-group {
  flex-wrap: wrap;
}

.main-row {
  margin-bottom: 0;
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.main-row :deep(.el-col) {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.avatar-wrapper {
  width: 100%;
  /* 固定一个视觉高度，让数字人大小稳定 */
  flex: 0 0 460px;
  margin-bottom: 12px;
  border-radius: 12px;
  overflow: hidden;
  background: #1a1a1a;
  border: 1px solid #e4e7ed;
}

.text-input-area {
  margin-top: 0;
  padding: 8px 0 0;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.input-hint {
  margin: 0 0 6px 0;
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  line-height: 1.5;
}

.textarea-wrapper {
  position: relative;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.textarea-wrapper:focus-within {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
}

.textarea-input :deep(.el-textarea__inner) {
  padding-right: 160px;
  padding-bottom: 52px;
  border: none;
  box-shadow: none;
  min-height: 140px;
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  resize: none;
}

.textarea-input :deep(.el-textarea__inner::placeholder) {
  color: #909399;
  opacity: 1;
}

.input-buttons {
  position: absolute;
  bottom: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 10;
}

.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.conversation-list {
  flex: 1 1 auto;
  /* 只在对话列表内部滚动 */
  overflow-y: auto;
  padding: 10px;
}

.message-item {
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.message-item.user {
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  text-align: right;
}

.message-item.assistant {
  background: linear-gradient(135deg, #f5f5f5 0%, #eeeeee 100%);
  text-align: left;
}

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 12px;
  color: #606266;
}

.message-content {
  word-break: break-word;
  line-height: 1.5;
  font-size: 14px;
}

.empty-message {
  text-align: center;
  color: #303133;
  padding: 32px 24px;
}

.empty-message .empty-icon {
  font-size: 40px;
  margin-bottom: 10px;
  color: #c0c4cc;
}

.empty-message p {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
}

.empty-message .empty-desc {
  font-size: 14px;
  color: #606266;
}

@media (max-width: 768px) {
  .voice-guide {
    padding: 8px;
    height: calc(100vh - 16px);
  }
  .avatar-wrapper {
    min-height: 280px;
  }
}
</style>
