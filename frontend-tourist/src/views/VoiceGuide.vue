<template>
  <div class="voice-guide">
    <!-- 角色选择 -->
    <el-card style="margin-bottom: 20px">
      <template #header>
        <h3>选择数字人角色</h3>
      </template>
      <el-radio-group v-model="selectedCharacterId" @change="handleCharacterChange">
        <el-radio-button
          v-for="character in characters"
          :key="character.id"
          :label="character.id"
        >
          {{ character.name }}
        </el-radio-button>
      </el-radio-group>
    </el-card>

    <el-row :gutter="20">
      <!-- 左侧：数字人展示区 -->
      <el-col :span="14">
        <el-card>
          <template #header>
            <div class="card-header">
              <h2>数字人导游</h2>
              <el-button
                type="text"
                @click="showHistory = !showHistory"
              >
                {{ showHistory ? '隐藏历史' : '查看历史' }}
              </el-button>
            </div>
          </template>
          
          <!-- 数字人容器：本地 Live2D 模型 -->
          <div class="avatar-wrapper">
            <Live2DCanvas character-name="Mao" character-group="free" />
          </div>

          <!-- 文本输入区（与录音入口放在一起） -->
          <div class="text-input-area under-avatar">
            <el-input
              v-model="textInput"
              type="textarea"
              :rows="3"
              placeholder="在此输入要对数字人说的话（支持中文），也可以点击右侧按钮开始录音"
              @keyup.enter.exact.prevent="handleSendText"
              @keyup.ctrl.enter.prevent="handleSendText"
            />
          </div>

          <!-- 控制按钮 -->
          <div class="control-buttons">
            <el-button
              type="primary"
              :icon="isRecording ? 'VideoPause' : 'Microphone'"
              @click="toggleRecording"
              :loading="processing"
              circle
            >
            </el-button>
            <el-button v-if="isSpeaking" @click="stopSpeaking">
              停止播报
            </el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：对话记录 -->
      <el-col :span="10">
        <el-card>
          <template #header>
            <h3>对话记录</h3>
          </template>
          
          <div class="conversation-list" ref="conversationListRef">
            <div
              v-for="(msg, index) in conversationHistory"
              :key="index"
              :class="['message-item', msg.role]"
            >
              <div class="message-header">
                <strong>{{ msg.role === 'user' ? '您' : 'AI导游' }}</strong>
                <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="message-content">{{ msg.content }}</div>
            </div>
            <div v-if="conversationHistory.length === 0" class="empty-message">
              还没有对话记录，开始与AI导游交流吧！
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
      <el-table :data="historyList" style="width: 100%">
        <el-table-column prop="query_text" label="问题" width="300" />
        <el-table-column prop="response_text" label="回答" />
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import Live2DCanvas from '../components/Live2DCanvas.vue'
import api from '../api'

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

let mediaRecorder = null
let audioChunks = []

// 初始化
onMounted(async () => {
  await loadCharacters()
  // 默认选择第一个角色
  if (characters.value.length > 0) {
    selectedCharacterId.value = characters.value[0].id
    currentAvatarId.value = characters.value[0].avatar_url || 'default'
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

// 角色切换
const handleCharacterChange = (characterId) => {
  const character = characters.value.find(c => c.id === characterId)
  if (character) {
    currentAvatarId.value = character.avatar_url || 'default'
    // 重新初始化数字人
    if (avatarRef.value) {
      avatarRef.value.destroy()
      nextTick(() => {
        avatarRef.value.init()
      })
    }
  }
}

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
    
    const answer = generateRes.data.answer
    sessionId.value = generateRes.data.session_id
    
    // 添加到对话历史
    addMessage('assistant', answer)
    
    // 3. 语音播报（使用 Edge TTS）
    const synthesizeRes = await api.post('/voice/synthesize', null, {
      params: {
        text: answer,
        method: 'edge'
      },
      responseType: 'blob'
    })
    const audioUrl = URL.createObjectURL(synthesizeRes.data)
    const audio = new Audio(audioUrl)
    isSpeaking.value = true
    audio.onended = () => {
      isSpeaking.value = false
    }
    audio.play()
    
    // 滚动到底部
    scrollToBottom()
  } catch (error) {
    const msg = error?.response?.data?.detail || error?.message || '未知错误'
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

    const answer = generateRes.data.answer
    sessionId.value = generateRes.data.session_id

    // 添加到对话历史
    addMessage('assistant', answer)

    // 语音播报（Edge TTS）
    const synthesizeRes = await api.post('/voice/synthesize', null, {
      params: {
        text: answer,
        method: 'edge'
      },
      responseType: 'blob'
    })
    const audioUrl = URL.createObjectURL(synthesizeRes.data)
    const audio = new Audio(audioUrl)
    isSpeaking.value = true
    audio.onended = () => {
      isSpeaking.value = false
    }
    audio.play()

    // 滚动到底部
    scrollToBottom()
  } catch (error) {
    const msg = error?.response?.data?.detail || error?.message || '未知错误'
    ElMessage.error('处理失败：' + msg)
    console.error('handleSendText error:', error)
  } finally {
    processing.value = false
  }
}

// 停止播报
const stopSpeaking = () => {
  // 当前实现使用浏览器 Audio 实例播放，简单地将状态重置即可
  isSpeaking.value = false
}

// 添加消息到对话历史
const addMessage = (role, content) => {
  conversationHistory.value.push({
    role,
    content,
    timestamp: new Date().toISOString()
  })
}

// 加载历史记录
const loadHistory = async () => {
  if (!sessionId.value) return
  
  try {
    const res = await api.get('/history/history', {
      params: {
        session_id: sessionId.value,
        limit: 50
      }
    })
    historyList.value = res.data
  } catch (error) {
    console.error('加载历史失败:', error)
  }
}

// 监听历史对话框显示
watch(showHistory, (val) => {
  if (val) {
    loadHistory()
  }
})

// 格式化时间
const formatTime = (timeStr) => {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN')
}

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    const listRef = document.querySelector('.conversation-list')
    if (listRef) {
      listRef.scrollTop = listRef.scrollHeight
    }
  })
}
</script>

<style scoped>
.voice-guide {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.avatar-wrapper {
  width: 100%;
  height: 500px;
  margin-bottom: 20px;
  border-radius: 8px;
  overflow: hidden;
}

.control-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.text-input-area {
  margin: 10px 0 0;
}

.text-input-area.under-avatar {
  margin-top: 0;
  margin-bottom: 10px;
}

.conversation-list {
  max-height: 600px;
  overflow-y: auto;
  padding: 10px;
}

.message-item {
  margin-bottom: 15px;
  padding: 10px;
  border-radius: 8px;
}

.message-item.user {
  background: #e3f2fd;
  text-align: right;
}

.message-item.assistant {
  background: #f5f5f5;
  text-align: left;
}

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 12px;
  color: #666;
}

.message-content {
  word-break: break-word;
}

.empty-message {
  text-align: center;
  color: #999;
  padding: 40px 0;
}
</style>
