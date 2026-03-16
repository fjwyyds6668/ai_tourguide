<template>
  <div class="voice-guide">
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
                  size="large"
                  :title="isRecording ? '停止录音' : '开始录音'"
                  style="min-width:44px;min-height:44px"
                />
                <el-button
                  type="primary"
                  @click="handleSendText"
                  :disabled="!textInput.trim() || processing"
                  size="large"
                  style="min-height:44px"
                >
                  发送
                </el-button>
                <el-button
                  v-if="isSpeaking"
                  @click="stopSpeaking"
                  size="large"
                  style="min-height:44px"
                >
                  停止播报
                </el-button>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

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
const MAX_HISTORY_LENGTH = 50
const conversationHistory = ref([])
const textInput = ref('')
const conversationListRef = ref(null)
let scrollRaf = 0

let mediaRecorder = null
let audioChunks = []

const audioQueue = [] // { url: string, blob?: Blob } — blob preferred to avoid re-fetch
let isPlayingQueue = false
let currentAudio = null
let ttsRequestQueue = Promise.resolve()
let ttsSessionId = 0
let ttsAbortController = null
let ragStreamAbortController = null

const currentScenic = ref(null)
const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || 'http://localhost:18000'
const getImageUrl = (url) => {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  if (url.startsWith('/')) return url
  return `${backendOrigin}${url}`
}

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
  if (lipSyncRafId) {
    cancelAnimationFrame(lipSyncRafId)
    lipSyncRafId = 0
  }
  ttsSessionId = 0
  audioQueue.forEach(item => {
    try {
      const url = item?.url || (typeof item === 'string' ? item : null)
      if (url) URL.revokeObjectURL(url)
    } catch (_) {}
  })
  audioQueue.length = 0
  try { ragStreamAbortController?.abort() } catch (_) {}
  try { ttsAbortController?.abort() } catch (_) {}
  try {
    Live2dManager.getInstance().setLipFactor(0)
  } catch (_) {}
})

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
    
    await streamGenerateAndSpeak(queryText, selectedCharacterId.value)
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

    await streamGenerateAndSpeak(queryText, selectedCharacterId.value)
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
  isSpeaking.value = false
  if (lipSyncRafId) {
    cancelAnimationFrame(lipSyncRafId)
    lipSyncRafId = 0
  }
  if (currentAudio) {
    currentAudio.pause()
    currentAudio = null
  }
  if (audioSource) {
    try { audioSource.stop() } catch (_) {}
    audioSource.disconnect()
    audioSource = null
  }
  if (analyser) {
    try { analyser.disconnect() } catch (_) {}
  }
  audioQueue.forEach(item => URL.revokeObjectURL(item?.url || item))
  audioQueue.length = 0
  isPlayingQueue = false
  ttsSessionId += 1
  try { ttsAbortController?.abort() } catch (_) {}
  try { ragStreamAbortController?.abort() } catch (_) {}
  ttsAbortController = null
  ragStreamAbortController = null
  
  try {
    const manager = Live2dManager.getInstance()
    if (manager) {
      manager.setLipFactor(0)
    }
  } catch (e) {
  }
}

const scenicBackgroundStyle = computed(() => {
  const full = getImageUrl(currentScenic.value?.cover_image_url)
  if (!full) return {}
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
let lipDataArray = null
let lipSyncRafId = 0

const initAudioAnalyzer = async () => {
  // 重建已关闭的 AudioContext
  if (audioContext && audioContext.state === 'closed') {
    audioContext = null
    analyser = null
    lipDataArray = null
  }
  if (!audioContext) {
    try {
      audioContext = new (window.AudioContext || window.webkitAudioContext)()
      analyser = audioContext.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.8
    } catch (e) {
      console.warn('音频上下文初始化失败:', e)
      throw e
    }
  }
  if (audioContext.state === 'suspended') {
    await audioContext.resume()
  }
}

const updateLipSync = () => {
  lipSyncRafId = 0
  if (!analyser || !isSpeaking.value) {
    return
  }

  if (!lipDataArray || lipDataArray.length !== analyser.frequencyBinCount) {
    lipDataArray = new Uint8Array(analyser.frequencyBinCount)
  }
  analyser.getByteFrequencyData(lipDataArray)

  let sum = 0
  for (let i = 0; i < lipDataArray.length; i++) {
    sum += lipDataArray[i] * lipDataArray[i]
  }
  const rms = Math.sqrt(sum / lipDataArray.length) / 255

  try {
    const manager = Live2dManager.getInstance()
    if (manager && manager.isReady()) {
      manager.setLipFactor(Math.min(rms * 1.5, 1.0))
    }
  } catch (e) {
  }

  if (isSpeaking.value) {
    lipSyncRafId = requestAnimationFrame(updateLipSync)
  }
}

const playAudioQueue = async () => {
  if (isPlayingQueue || audioQueue.length === 0) {
    return
  }

  isPlayingQueue = true
  isSpeaking.value = true
  
  try {
    await initAudioAnalyzer()
  } catch (e) {
    console.warn('音频上下文初始化失败，将使用降级播放:', e)
  }

  while (audioQueue.length > 0) {
    const item = audioQueue.shift()
    const audioUrl = item?.url || item
    const isLastChunk = audioQueue.length === 0
    try {
      await new Promise((resolve, reject) => {
        const toArrayBuffer = () => {
          if (item?.blob && typeof item.blob.arrayBuffer === 'function') return item.blob.arrayBuffer()
          return fetch(audioUrl).then(r => r.arrayBuffer())
        }
        toArrayBuffer()
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
                if (lipSyncRafId) cancelAnimationFrame(lipSyncRafId)
                lipSyncRafId = requestAnimationFrame(updateLipSync)
                
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
        try { URL.revokeObjectURL(audioUrl) } catch (_) {}
      }
    }
  }

  currentAudio = null
  audioSource = null
  isPlayingQueue = false
  isSpeaking.value = false
}

const synthesizeAndQueue = async (text, characterId, sessionId, useStreamApi = false) => {
  if (!text || typeof text !== 'string' || text.length === 0) {
    console.warn('TTS 合成跳过：文本为空或无效', text)
    return
  }

  const cleanedText = text.replace(/\s+/g, ' ').trim()
  if (cleanedText.length === 0) {
    console.warn('TTS 合成跳过：清理后文本为空')
    return
  }

  const synthesizeUrl = useStreamApi ? '/voice/synthesize-stream' : '/voice/synthesize'
  ttsRequestQueue = ttsRequestQueue.then(async () => {
    if (sessionId !== ttsSessionId) {
      return
    }
    try {
      if (!ttsAbortController && typeof AbortController !== 'undefined') {
        ttsAbortController = new AbortController()
      }
      const synthesizeRes = await api.post(
        synthesizeUrl,
        { 
          text: cleanedText, 
          character_id: characterId 
        },
        { responseType: 'blob', timeout: 30000, signal: ttsAbortController?.signal }
      )
      if (sessionId !== ttsSessionId) {
        return
      }

      if (!synthesizeRes.data || synthesizeRes.data.size === 0) {
        console.warn('TTS 返回空音频数据，文本:', cleanedText.substring(0, 50))
        return
      }
      const blob = synthesizeRes.data
      const audioUrl = URL.createObjectURL(blob)
      audioQueue.push({ url: audioUrl, blob })
      playAudioQueue()
    } catch (error) {
      console.warn('TTS 合成失败，已静默跳过:', error?.message || error, '文本:', cleanedText.substring(0, 50))
    }
  }).catch(error => {
    console.error('TTS 队列执行失败:', error)
  })
}

const streamGenerateAndSpeak = async (queryText, characterId) => {
  const msgIndex = conversationHistory.value.length
  conversationHistory.value.push({
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString()
  })
  const thisTtsSessionId = ++ttsSessionId
  ttsRequestQueue = Promise.resolve()

  const baseURL = api.defaults.baseURL || '/api/v1'
  const url = `${baseURL}/rag/generate-stream`
  const body = JSON.stringify({
    query: queryText,
    session_id: sessionId.value || undefined,
    character_id: characterId ?? selectedCharacterId.value,
    use_rag: true,
    scenic_name: currentScenic.value?.name || undefined
  })

  const msgRef = conversationHistory.value[msgIndex]
  let pendingText = ''
  let flushRaf = 0
  const scheduleFlush = () => {
    if (flushRaf) return
    flushRaf = requestAnimationFrame(() => {
      flushRaf = 0
      if (!msgRef) return
      if (pendingText) {
        msgRef.content = (msgRef.content || '') + pendingText
        pendingText = ''
      }
      scrollToBottom()
    })
  }
  try {
    try { ragStreamAbortController?.abort() } catch (_) {}
    ragStreamAbortController = typeof AbortController !== 'undefined' ? new AbortController() : null
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      signal: ragStreamAbortController?.signal,
    })
    if (!resp.ok) {
      const errText = await resp.text()
      throw new Error(errText || `请求失败 ${resp.status}`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          const type = data.type
          const content = data.content
          if (type === 'session_id' && content) {
            sessionId.value = content
          } else if (type === 'text' && content && msgRef) {
            pendingText += content
            scheduleFlush()
          } else if (type === 'audio' && content) {
            if (ttsSessionId !== thisTtsSessionId) return
            try {
              const binary = atob(content)
              const bytes = new Uint8Array(binary.length)
              for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
              const blob = new Blob([bytes], { type: 'audio/wav' })
              const audioUrl = URL.createObjectURL(blob)
              audioQueue.push({ url: audioUrl, blob })
              playAudioQueue()
            } catch (e) {
              console.warn('解析流式音频失败:', e)
            }
          } else if (type === 'tts' && content && content.trim()) {
            synthesizeAndQueue(content.trim(), characterId ?? selectedCharacterId.value, thisTtsSessionId, true)
          } else if (type === 'done') {
            if (pendingText) {
              msgRef.content = (msgRef.content || '') + pendingText
              pendingText = ''
            }
            if (msgRef && content) msgRef.content = content
            scrollToBottom()
          } else if (type === 'error' && content) {
            ElMessage.error(content)
          }
        } catch (e) {
        }
      }
    }
    if (buffer.trim()) {
      const line = buffer.replace(/^data: /, '')
      try {
        const data = JSON.parse(line)
        if (data.type === 'text' && data.content && msgRef) {
          pendingText += data.content
        }
        if (data.type === 'audio' && data.content && ttsSessionId === thisTtsSessionId) {
          try {
            const binary = atob(data.content)
            const bytes = new Uint8Array(binary.length)
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
            const blob = new Blob([bytes], { type: 'audio/wav' })
            const audioUrl = URL.createObjectURL(blob)
            audioQueue.push({ url: audioUrl, blob })
            playAudioQueue()
          } catch (_) {}
        }
        if (data.type === 'tts' && data.content && data.content.trim()) {
          synthesizeAndQueue(data.content.trim(), characterId ?? selectedCharacterId.value, thisTtsSessionId, true)
        }
      } catch (_) {}
    }
    if (pendingText && msgRef) {
      msgRef.content = (msgRef.content || '') + pendingText
      pendingText = ''
    }
    scrollToBottom()
  } catch (err) {
    if (msgRef) msgRef.content = (msgRef.content || '') + '\n[ 生成出错：' + (err.message || '未知错误') + ' ]'
    scrollToBottom()
    throw err
  }
}

const addAssistantStreamMessage = (fullText, characterId = null) => {
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
  const TTS_CHUNK_SIZE = 80
  const TTS_AHEAD_THRESHOLD = 20
  let ttsSynthesizedLength = 0

  ttsRequestQueue = Promise.resolve()
  const initialChunkEnd = Math.min(TTS_CHUNK_SIZE, textLength)
  const initialText = fullText.substring(0, initialChunkEnd)
  if (initialText.trim()) {
    synthesizeAndQueue(initialText, characterId || selectedCharacterId.value, thisTtsSessionId)
    ttsSynthesizedLength = initialChunkEnd
  }

  let rafId = 0
  const step = () => {
    if (ttsSessionId !== thisTtsSessionId) {
      if (rafId) cancelAnimationFrame(rafId)
      rafId = 0
      return
    }
    if (i >= textLength) {
      if (rafId) cancelAnimationFrame(rafId)
      rafId = 0
      return
    }
    const msg = conversationHistory.value[index]
    if (!msg) {
      if (rafId) cancelAnimationFrame(rafId)
      rafId = 0
      return
    }
    const chunkSize = Math.min(12, textLength - i)
    msg.content += fullText.substring(i, i + chunkSize)
    i += chunkSize

    if (i >= ttsSynthesizedLength - TTS_AHEAD_THRESHOLD && ttsSynthesizedLength < textLength) {
      const nextChunkStart = ttsSynthesizedLength
      const nextChunkEnd = Math.min(ttsSynthesizedLength + TTS_CHUNK_SIZE, textLength)
      let nextChunk = fullText.substring(nextChunkStart, nextChunkEnd)
      if (nextChunk.trim().length === 0) {
        rafId = requestAnimationFrame(step)
        return
      }

      if (nextChunkEnd === textLength) {
        const lastChar = nextChunk[nextChunk.length - 1]
        if (!['。', '！', '？', '.', '!', '?'].includes(lastChar)) {
          nextChunk = nextChunk + '。'
        }
      }

      synthesizeAndQueue(nextChunk, characterId || selectedCharacterId.value, thisTtsSessionId)
      ttsSynthesizedLength = nextChunkEnd
    }
    rafId = requestAnimationFrame(step)
  }
  rafId = requestAnimationFrame(step)
}

const scrollToBottom = () => {
  if (!conversationListRef.value) return
  if (scrollRaf) return
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = 0
    const el = conversationListRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
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
  flex: 0 0 min(460px, 45vh);
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
  overflow-y: auto;
  padding: 10px;
  -webkit-overflow-scrolling: touch;
}

.message-item {
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  content-visibility: auto;
  contain-intrinsic-size: auto 80px;
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
    height: auto;
    min-height: calc(100vh - 16px);
    overflow: visible;
  }
  .voice-guide .main-row {
    flex: none;
    overflow: visible;
    min-height: 0;
  }
  .avatar-wrapper {
    flex: 0 0 auto;
    min-height: 240px;
    height: min(42vh, 360px);
    max-height: 50vh;
  }
  .textarea-input :deep(.el-textarea__inner) {
    padding-right: 10px;
    padding-bottom: 56px;
    min-height: 80px;
    font-size: 16px;
  }
  .input-buttons {
    gap: 6px;
  }
  .input-buttons .el-button {
    min-width: 44px;
    min-height: 44px;
  }
}

@media (max-width: 480px) {
  .voice-guide {
    padding: 4px;
  }
  .avatar-wrapper {
    min-height: 200px;
    height: min(38vh, 280px);
  }
  .textarea-input :deep(.el-textarea__inner) {
    min-height: 60px;
  }
  .role-card {
    margin-bottom: 8px;
  }
}

@media (max-height: 500px) and (orientation: landscape) {
  .voice-guide {
    height: auto;
    overflow: auto;
    min-height: 100vh;
  }
  .avatar-wrapper {
    flex: 0 0 auto;
    min-height: 150px;
    height: min(80vw, 220px);
    max-height: 220px;
  }
  .role-card {
    display: none;
  }
  .conversation-list {
    max-height: 180px;
  }
  .main-row :deep(.el-row) {
    flex-direction: row !important;
  }
}
</style>
