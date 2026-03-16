<template>
  <div class="voice-guide">
    <!-- Role selection strip -->
    <div class="role-strip">
      <span class="role-label">选择导游角色：</span>
      <el-radio-group v-model="selectedCharacterId" @change="handleCharacterChange" class="role-group">
        <el-radio-button
          v-for="character in characters"
          :key="character.id"
          :label="character.id"
        >
          {{ character.name }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <div class="main-area">
      <!-- Left: Avatar -->
      <div class="avatar-panel">
        <div class="avatar-wrapper" :style="scenicBackgroundStyle">
          <Live2DCanvas
            :character-name="currentLive2DName"
            :character-group="currentLive2DGroup"
          />
        </div>
      </div>

      <!-- Right: Chat -->
      <div class="chat-panel">
        <!-- Messages -->
        <div class="chat-messages" ref="conversationListRef">
          <div v-if="conversationHistory.length === 0" class="empty-chat">
            <el-icon class="empty-icon"><ChatDotRound /></el-icon>
            <p class="empty-title">开始与 AI 导游对话吧</p>
            <p class="empty-desc">输入文字或点击麦克风语音提问</p>
          </div>

          <template v-for="(msg, index) in conversationHistory" :key="`${msg.timestamp}-${index}`">
            <!-- User message: right-aligned -->
            <div v-if="msg.role === 'user'" class="message-row user-row">
              <div class="bubble user-bubble">
                <div class="bubble-text">{{ msg.content }}</div>
                <div class="bubble-time">{{ formatTime(msg.timestamp) }}</div>
              </div>
              <div class="avatar-dot user-dot">您</div>
            </div>

            <!-- Assistant message: left-aligned -->
            <div v-else class="message-row ai-row">
              <div class="avatar-dot ai-dot">导</div>
              <div class="bubble ai-bubble">
                <div class="bubble-text">{{ msg.content }}<span v-if="msg.content === '' && index === conversationHistory.length - 1" class="typing-cursor">|</span></div>
                <div class="bubble-time">{{ formatTime(msg.timestamp) }}</div>
              </div>
            </div>
          </template>
        </div>

        <!-- Input area -->
        <div class="input-area">
          <div class="textarea-wrapper" :class="{ focused: inputFocused }">
            <el-input
              v-model="textInput"
              type="textarea"
              :rows="2"
              placeholder="在此输入问题… (Enter 发送，Ctrl+Enter 换行)"
              @keyup.enter.exact.prevent="handleSendText"
              @keyup.ctrl.enter.prevent="() => textInput += '\n'"
              @focus="inputFocused = true"
              @blur="inputFocused = false"
              class="chat-input"
            />
            <div class="input-buttons">
              <el-button
                :type="isRecording ? 'danger' : 'primary'"
                :icon="isRecording ? 'VideoPause' : 'Microphone'"
                @click="toggleRecording"
                :loading="processing && !isRecording"
                circle
                size="default"
                :title="isRecording ? '停止录音' : '开始录音'"
              />
              <el-button
                v-if="isSpeaking"
                @click="stopSpeaking"
                size="default"
                plain
              >停止播报</el-button>
              <el-button
                type="primary"
                @click="handleSendText"
                :disabled="!textInput.trim() || processing"
                size="default"
              >发送</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
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
const inputFocused = ref(false)
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
            // 保存 session_id 到 localStorage，用于历史记录按用户过滤
            try {
              const savedIds = JSON.parse(localStorage.getItem('tourguide_session_ids') || '[]')
              if (!savedIds.includes(content)) {
                savedIds.push(content)
                localStorage.setItem('tourguide_session_ids', JSON.stringify(savedIds))
              }
            } catch (_) {}
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
  gap: 10px;
}

/* ── Role strip ── */
.role-strip {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 10px;
  padding: 10px 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  border: 1px solid #f0f0f0;
}

.role-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.role-group {
  flex-wrap: wrap;
}

/* ── Main area ── */
.main-area {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── Avatar panel ── */
.avatar-panel {
  flex: 0 0 42%;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.avatar-wrapper {
  width: 100%;
  flex: 1;
  border-radius: 14px;
  overflow: hidden;
  background: #1a1a1a;
  border: 1px solid #e4e7ed;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

/* ── Chat panel ── */
.chat-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 14px;
  border: 1px solid #f0f0f0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: hidden;
}

/* ── Messages area ── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  -webkit-overflow-scrolling: touch;
}

.chat-messages::-webkit-scrollbar {
  width: 4px;
}
.chat-messages::-webkit-scrollbar-thumb {
  background: #dcdfe6;
  border-radius: 4px;
}

/* Empty state */
.empty-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  padding: 40px 20px;
  gap: 8px;
}

.empty-chat .empty-icon {
  font-size: 48px;
  color: #dcdfe6;
}

.empty-chat .empty-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #909399;
}

.empty-chat .empty-desc {
  margin: 0;
  font-size: 13px;
  color: #c0c4cc;
}

/* Message rows */
.message-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.user-row {
  align-self: flex-end;
  flex-direction: row;
  max-width: 88%;
}

.ai-row {
  align-self: flex-start;
  flex-direction: row;
  max-width: 88%;
}

/* Avatar dots */
.avatar-dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.user-dot {
  background: linear-gradient(135deg, #409eff, #66b1ff);
  color: #fff;
}

.ai-dot {
  background: linear-gradient(135deg, #67c23a, #85ce61);
  color: #fff;
}

/* Bubbles */
.bubble {
  padding: 10px 14px;
  border-radius: 16px;
  max-width: 100%;
  word-break: break-word;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

.user-bubble {
  background: linear-gradient(135deg, #409eff, #66b1ff);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.ai-bubble {
  background: #f4f6f8;
  color: #303133;
  border-bottom-left-radius: 4px;
  border: 1px solid #ebeef5;
}

.bubble-text {
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  min-height: 1.65em;
}

.bubble-time {
  font-size: 11px;
  margin-top: 5px;
  opacity: 0.65;
}

.user-bubble .bubble-time {
  color: rgba(255,255,255,0.85);
  text-align: right;
}

.ai-bubble .bubble-time {
  color: #909399;
  text-align: left;
}

/* Typing cursor animation */
.typing-cursor {
  display: inline-block;
  animation: blink 0.8s step-end infinite;
  color: #409eff;
  font-weight: 700;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ── Input area ── */
.input-area {
  flex-shrink: 0;
  padding: 10px 12px 12px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

.textarea-wrapper {
  border: 1.5px solid #dcdfe6;
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
  background: #fff;
}

.textarea-wrapper.focused {
  border-color: #409eff;
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.1);
}

.chat-input :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  resize: none;
  padding: 10px 12px 6px;
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  background: transparent;
}

.chat-input :deep(.el-textarea__inner::placeholder) {
  color: #c0c4cc;
}

.input-buttons {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 6px 10px 8px;
  background: #fff;
  border-top: 1px solid #f5f5f5;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .voice-guide {
    padding: 8px;
    height: auto;
    min-height: calc(100vh - 16px);
    overflow: visible;
  }

  .main-area {
    flex-direction: column;
    overflow: visible;
    flex: none;
  }

  .avatar-panel {
    flex: none;
    height: min(42vh, 340px);
  }

  .avatar-wrapper {
    height: 100%;
  }

  .chat-panel {
    min-height: 420px;
  }

  .chat-messages {
    max-height: 50vh;
  }
}

@media (max-width: 480px) {
  .voice-guide {
    padding: 4px;
    gap: 6px;
  }

  .role-strip {
    padding: 8px 12px;
  }

  .avatar-panel {
    height: min(38vh, 280px);
  }

  .user-row, .ai-row {
    max-width: 95%;
  }
}

@media (max-height: 500px) and (orientation: landscape) {
  .voice-guide {
    height: auto;
    overflow: auto;
  }

  .avatar-panel {
    flex: 0 0 38%;
  }
}
</style>
