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
              <el-button
                type="primary"
                link
                @click="showHistory = !showHistory"
                class="history-btn"
              >
                <el-icon><Document /></el-icon>
                <span>{{ showHistory ? '隐藏历史' : '查看历史' }}</span>
              </el-button>
            </div>
          </template>
          
          <div class="avatar-wrapper">
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

    <!-- 历史记录对话框 -->
    <el-dialog
      v-model="showHistory"
      title="历史记录"
      width="800px"
    >
      <el-table
        :data="historyList"
        v-loading="historyLoading"
        style="width: 100%"
        :row-key="(row) => row.id ?? row.created_at + row.query_text"
      >
        <el-table-column prop="query_text" label="问题" width="300" />
        <el-table-column prop="response_text" label="回答" />
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无历史记录，开始与AI导游对话后会显示在这里" />
        </template>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, ChatDotRound } from '@element-plus/icons-vue'
import Live2DCanvas from '../components/Live2DCanvas.vue'
import api from '../api'
import { formatTime } from '../utils/format'
import { Live2dManager } from '../lib/live2d/live2dManager'
import { LAppDelegate } from '../lib/live2d/src/lappdelegate'

// 状态管理
const isRecording = ref(false)
const isSpeaking = ref(false)
const processing = ref(false)
const selectedCharacterId = ref(null)
const sessionId = ref(null)
const characters = ref([])
const conversationHistory = ref([])
const textInput = ref('')
const showHistory = ref(false)
const historyList = ref([])
const historyLoading = ref(false)

let mediaRecorder = null
let audioChunks = []

// TTS 音频队列管理
const audioQueue = []
let isPlayingQueue = false
let currentAudio = null
let ttsRequestQueue = Promise.resolve() // TTS 请求队列，确保按顺序执行

// 初始化
onMounted(async () => {
  await loadCharacters()
  // 默认选择第一个角色
  if (characters.value.length > 0) {
    selectedCharacterId.value = characters.value[0].id
  }
})

// 加载角色列表
const loadCharacters = async () => {
  try {
    const res = await api.get('/characters/characters', {
      params: { active_only: true }
    })
    characters.value = res.data
  } catch (error) {
    console.error('加载角色失败:', error)
    ElMessage.error('加载角色失败')
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

// 录音控制
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

// 处理音频
const processAudio = async (audioBlob) => {
  processing.value = true
  try {
    // 1. 语音识别
    const formData = new FormData()
    formData.append('file', audioBlob, 'audio.wav')
    formData.append('method', 'whisper')
    
    const transcribeRes = await api.post('/voice/transcribe', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    const queryText = transcribeRes.data.text
    
    // 添加到对话历史
    addMessage('user', queryText)
    
    // 2. RAG 生成回答（支持多轮对话）
    const generateRes = await api.post('/rag/generate', {
      query: queryText,
      session_id: sessionId.value,
      character_id: selectedCharacterId.value,
      use_rag: true
    })
    
    const answer = generateRes.data.answer || ''
    sessionId.value = generateRes.data.session_id
    
    // 以"流式打字"方式展示助手回复，同时进行 TTS 合成和播放
    addAssistantStreamMessage(answer, selectedCharacterId.value)
    
    // 滚动到底部
    scrollToBottom()
  } catch (error) {
    const msg = await extractErrorMessage(error)
    ElMessage.error('处理失败：' + msg)
    console.error('processAudio error:', error)
  } finally {
    processing.value = false
  }
}

// 处理纯文本输入
const handleSendText = async () => {
  const queryText = textInput.value.trim()
  if (!queryText) {
    ElMessage.warning('请输入要对数字人说的话')
    return
  }

  processing.value = true
  textInput.value = ''
  try {
    // 添加到对话历史
    addMessage('user', queryText)

    // 调用同一套 RAG + 硅基模型
    const generateRes = await api.post('/rag/generate', {
      query: queryText,
      session_id: sessionId.value,
      character_id: selectedCharacterId.value,
      use_rag: true
    })

    const answer = generateRes.data.answer || ''
    sessionId.value = generateRes.data.session_id

    // 触发说话动作和表情
    triggerSpeakingMotion()

    // 以"流式打字"方式展示助手回复，同时进行 TTS 合成和播放
    addAssistantStreamMessage(answer, selectedCharacterId.value)

    // 滚动到底部
    scrollToBottom()
  } catch (error) {
    const msg = await extractErrorMessage(error)
    ElMessage.error('处理失败：' + msg)
    console.error('handleSendText error:', error)
  } finally {
    processing.value = false
  }
}

// 从后端错误响应中提取可读的错误信息（兼容 blob）
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

// 停止播报
const stopSpeaking = () => {
  // 停止当前播放的音频
  if (currentAudio) {
    currentAudio.pause()
    currentAudio = null
  }
  if (audioSource) {
    audioSource.stop()
    audioSource.disconnect()
    audioSource = null
  }
  // 清空队列
  audioQueue.forEach(url => URL.revokeObjectURL(url))
  audioQueue.length = 0
  isPlayingQueue = false
  isSpeaking.value = false
  
  // 重置嘴巴同步
  try {
    const manager = Live2dManager.getInstance()
    if (manager) {
      manager.setLipFactor(0)
    }
  } catch (e) {
    // 忽略
  }
}

// 添加消息到对话历史
const addMessage = (role, content) => {
  conversationHistory.value.push({
    role,
    content,
    timestamp: new Date().toISOString()
  })
}

// 音频分析器（用于嘴巴同步）
let audioContext = null
let analyser = null
let audioSource = null

// 初始化音频分析器
const initAudioAnalyzer = () => {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)()
    analyser = audioContext.createAnalyser()
    analyser.fftSize = 256
    analyser.smoothingTimeConstant = 0.8
  }
}

// 控制 Live2D 嘴巴同步
const updateLipSync = () => {
  if (!analyser || !isSpeaking.value) {
    return
  }
  
  const dataArray = new Uint8Array(analyser.frequencyBinCount)
  analyser.getByteFrequencyData(dataArray)
  
  // 计算音频强度（RMS）
  let sum = 0
  for (let i = 0; i < dataArray.length; i++) {
    sum += dataArray[i] * dataArray[i]
  }
  const rms = Math.sqrt(sum / dataArray.length) / 255
  
  // 控制 Live2D 嘴巴参数（通过 Live2dManager）
  try {
    const manager = Live2dManager.getInstance()
    if (manager && manager.isReady()) {
      // 设置嘴巴同步因子（0-1）
      manager.setLipFactor(Math.min(rms * 2, 1.0))
    }
  } catch (e) {
    // Live2D 未加载时忽略
  }
  
  // 继续更新
  if (isSpeaking.value) {
    requestAnimationFrame(updateLipSync)
  }
}

// 播放音频队列（带嘴巴同步）
const playAudioQueue = async () => {
  if (isPlayingQueue || audioQueue.length === 0) {
    return
  }

  isPlayingQueue = true
  isSpeaking.value = true
  
  // 初始化音频分析器
  initAudioAnalyzer()

  while (audioQueue.length > 0) {
    const audioUrl = audioQueue.shift()
    try {
      await new Promise((resolve, reject) => {
        // 使用 fetch 获取音频数据
        fetch(audioUrl)
          .then(response => response.arrayBuffer())
          .then(arrayBuffer => {
            // 解码音频
            audioContext.decodeAudioData(arrayBuffer)
              .then(audioBuffer => {
                // 创建音频源
                if (audioSource) {
                  audioSource.disconnect()
                }
                audioSource = audioContext.createBufferSource()
                audioSource.buffer = audioBuffer
                
                // 连接到分析器
                audioSource.connect(analyser)
                analyser.connect(audioContext.destination)
                
                // 开始播放
                audioSource.start(0)
                
                // 开始嘴巴同步更新
                updateLipSync()
                
                // 监听播放结束
                audioSource.onended = () => {
                  URL.revokeObjectURL(audioUrl)
                  resolve()
                }
                
                currentAudio = {
                  pause: () => {
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
      // 如果 Web Audio API 失败，回退到普通播放
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

// 合成并添加 TTS 到队列（按顺序执行，确保顺序正确）
const synthesizeAndQueue = async (text, characterId) => {
  if (!text || text.length === 0) {
    return
  }

  // 将 TTS 请求加入队列，确保按顺序执行
  ttsRequestQueue = ttsRequestQueue.then(async () => {
    try {
      const synthesizeRes = await api.post(
        '/voice/synthesize',
        { 
          text: text, 
          character_id: characterId 
        },
        { responseType: 'blob' }
      )
      const audioUrl = URL.createObjectURL(synthesizeRes.data)
      audioQueue.push(audioUrl)
      playAudioQueue()
    } catch (error) {
      console.error('TTS 合成失败:', error)
    }
  }).catch(error => {
    console.error('TTS 队列执行失败:', error)
  })
}

// “流式打字”方式添加助手消息（流式显示文本的同时按顺序合成和播放 TTS）
const addAssistantStreamMessage = (fullText, characterId = null) => {
  const index = conversationHistory.value.length
  conversationHistory.value.push({
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString()
  })

  if (!fullText) {
    return
  }

  // 重置 TTS 请求队列
  ttsRequestQueue = Promise.resolve()

  const chars = Array.from(fullText)
  let i = 0
  const interval = 15 // 毫秒（加快显示速度）
  const TTS_CHUNK_SIZE = 30 // 每 30 个字符合成一次 TTS
  let ttsSynthesizedLength = 0 // 已合成 TTS 的文本长度

  // 在文本显示到一定长度时开始第一次 TTS
  const startFirstTTS = () => {
    const initialText = fullText.substring(0, Math.min(TTS_CHUNK_SIZE, fullText.length))
    if (initialText.trim()) {
      synthesizeAndQueue(initialText, characterId || selectedCharacterId.value)
      ttsSynthesizedLength = initialText.length
    }
  }

  // 延迟一小段时间后开始第一次 TTS，让文本先显示一些
  setTimeout(startFirstTTS, 200)

  const timer = setInterval(() => {
    if (i >= chars.length) {
      clearInterval(timer)
      // 确保最后剩余的文本也被合成，避免“最后几个字没读出来”
      if (ttsSynthesizedLength < fullText.length) {
        let remainingText = fullText.substring(ttsSynthesizedLength).trim()
        if (remainingText) {
          // 最后一段过短时 TTS 易截断，补句号并保证至少几个字，减少漏读
          if (remainingText.length <= 6 && remainingText[remainingText.length - 1] !== '。' && remainingText[remainingText.length - 1] !== '！' && remainingText[remainingText.length - 1] !== '？') {
            remainingText = remainingText + '。'
          }
          synthesizeAndQueue(remainingText, characterId || selectedCharacterId.value)
        }
      }
      return
    }
    const msg = conversationHistory.value[index]
    if (!msg) {
      clearInterval(timer)
      return
    }
    msg.content += chars[i]
    i += 1

    // 当文本显示到下一个 TTS 块的位置时，触发下一段 TTS
    // 提前一点触发，让 TTS 合成和文本显示更同步
    if (i >= ttsSynthesizedLength + TTS_CHUNK_SIZE - 5 && i < fullText.length) {
      const nextChunkStart = ttsSynthesizedLength
      const nextChunkEnd = Math.min(ttsSynthesizedLength + TTS_CHUNK_SIZE, fullText.length)
      const nextChunk = fullText.substring(nextChunkStart, nextChunkEnd)
      if (nextChunk.trim()) {
        synthesizeAndQueue(nextChunk, characterId || selectedCharacterId.value)
        ttsSynthesizedLength = nextChunkEnd
      }
    }
  }, interval)
}

// 加载历史记录
const loadHistory = async () => {
  if (!sessionId.value) {
    historyList.value = []
    return
  }
  historyLoading.value = true
  try {
    const res = await api.get('/history/history', {
      params: {
        session_id: sessionId.value,
        limit: 5
      }
    })
    historyList.value = res.data?.data ?? res.data ?? []
  } catch (error) {
    console.error('加载历史失败:', error)
    historyList.value = []
  } finally {
    historyLoading.value = false
  }
}

// 监听历史对话框显示
watch(showHistory, (val) => {
  if (val) {
    loadHistory()
  }
})

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    const listRef = document.querySelector('.conversation-list')
    if (listRef) {
      listRef.scrollTop = listRef.scrollHeight
    }
  })
}

// 触发说话动作和表情
const triggerSpeakingMotion = () => {
  try {
    const delegate = LAppDelegate.getInstance()
    if (!delegate) return
    
    // 获取模型管理器
    const subdelegates = delegate._subdelegates
    if (!subdelegates || subdelegates.getSize() === 0) return
    
    const subdelegate = subdelegates.at(0)
    const live2dManager = subdelegate?._live2dManager
    if (!live2dManager) return
    
    const models = live2dManager._models
    if (!models || models.getSize() === 0) return
    
    const model = models.at(0)
    if (!model) return
    
    // 触发说话动作（随机选择 TapBody 动作）
    const motionGroup = 'TapBody'
    const modelSetting = model._modelSetting
    if (modelSetting) {
      const motionCount = modelSetting.getMotionCount(motionGroup) || 0
      if (motionCount > 0) {
        const motionNo = Math.floor(Math.random() * motionCount)
        model.startMotion(motionGroup, motionNo, 2) // priority = 2
      }
      
      // 设置微笑表情
      const expressionCount = modelSetting.getExpressionCount() || 0
      if (expressionCount > 0) {
        // 尝试找到微笑表情
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
  padding: 20px;
}

.section-card {
  margin-bottom: 20px;
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.section-card :deep(.el-card__header) {
  padding: 14px 20px;
  font-weight: 600;
  border-bottom: 1px solid #f0f0f0;
}

.card-title {
  font-size: 16px;
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
  margin-bottom: 20px;
}

.role-group {
  flex-wrap: wrap;
}

.main-row {
  margin-bottom: 20px;
}

.avatar-wrapper {
  width: 100%;
  height: 420px;
  margin-bottom: 16px;
  border-radius: 12px;
  overflow: hidden;
  background: #1a1a1a;
  border: 1px solid #e4e7ed;
}

.text-input-area {
  margin-top: 0;
  padding: 12px 0 0;
  border-top: 1px solid #f0f0f0;
}

.input-hint {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: #909399;
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

.conversation-list {
  max-height: 560px;
  min-height: 280px;
  overflow-y: auto;
  padding: 12px;
}

.message-item {
  margin-bottom: 14px;
  padding: 12px 14px;
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
  margin-bottom: 6px;
  font-size: 12px;
  color: #606266;
}

.message-content {
  word-break: break-word;
  line-height: 1.5;
}

.empty-message {
  text-align: center;
  color: #909399;
  padding: 48px 24px;
}

.empty-message .empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  color: #c0c4cc;
}

.empty-message p {
  margin: 0 0 6px 0;
  font-size: 14px;
}

.empty-message .empty-desc {
  font-size: 12px;
  color: #c0c4cc;
}

@media (max-width: 768px) {
  .voice-guide {
    padding: 12px;
  }
  .avatar-wrapper {
    height: 320px;
  }
}
</style>
