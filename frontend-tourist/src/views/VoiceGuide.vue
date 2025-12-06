<template>
  <div class="voice-guide">
    <el-card>
      <template #header>
        <h2>语音导览</h2>
      </template>
      
      <div class="voice-container">
        <el-button
          type="primary"
          :icon="isRecording ? 'VideoPause' : 'Microphone'"
          size="large"
          @click="toggleRecording"
          :loading="processing"
        >
          {{ isRecording ? '停止录音' : '开始录音' }}
        </el-button>
        
        <div v-if="transcribedText" class="transcription">
          <h3>您说：</h3>
          <p>{{ transcribedText }}</p>
        </div>
        
        <div v-if="responseText" class="response">
          <h3>AI 导游回复：</h3>
          <p>{{ responseText }}</p>
        </div>
        
        <div v-if="audioUrl" class="audio-player">
          <audio :src="audioUrl" controls autoplay></audio>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const isRecording = ref(false)
const processing = ref(false)
const transcribedText = ref('')
const responseText = ref('')
const audioUrl = ref('')
let mediaRecorder = null
let audioChunks = []

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
    // 语音识别
    const formData = new FormData()
    formData.append('file', audioBlob, 'audio.wav')
    formData.append('method', 'whisper')
    
    const transcribeRes = await api.post('/voice/transcribe', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    transcribedText.value = transcribeRes.data.text
    
    // RAG 检索生成回复
    const ragRes = await api.post('/rag/search', {
      query: transcribedText.value,
      top_k: 5
    })
    
    // 简单处理：使用第一个结果作为回复
    if (ragRes.data.vector_results && ragRes.data.vector_results.length > 0) {
      responseText.value = `根据您的问题，我为您找到了相关信息...`
    } else {
      responseText.value = '抱歉，我没有找到相关信息。'
    }
    
    // 语音合成
    const synthesizeRes = await api.post('/voice/synthesize', null, {
      params: {
        text: responseText.value,
        method: 'edge'
      },
      responseType: 'blob'
    })
    
    audioUrl.value = URL.createObjectURL(synthesizeRes.data)
  } catch (error) {
    ElMessage.error('处理失败：' + error.message)
    console.error(error)
  } finally {
    processing.value = false
  }
}
</script>

<style scoped>
.voice-guide {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

.voice-container {
  text-align: center;
  padding: 40px 0;
}

.transcription,
.response {
  margin: 30px 0;
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
  text-align: left;
}

.audio-player {
  margin-top: 20px;
}
</style>

