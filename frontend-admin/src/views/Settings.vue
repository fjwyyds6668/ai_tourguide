<template>
  <div class="page-wrap">
    <h1 class="admin-page-title"><el-icon><Setting /></el-icon> 系统设置</h1>
    <el-card title="TTS 语音合成配置" style="margin-top: 24px" v-loading="loading">
      <template #header>TTS 语音合成配置</template>
      <el-alert
        title="配置说明"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 24px"
      >
        修改配置后需要重启后端服务才能生效。当前系统仅使用在线科大讯飞 TTS 进行语音合成。
      </el-alert>
      <el-form ref="formRef" :model="config" label-position="top" @submit.prevent="handleSave">
        <el-form-item label="默认讯飞音色（XFYUN_VOICE）">
          <el-select
            v-model="config.xfyun_voice"
            placeholder="选择默认讯飞音色"
            filterable
            style="width: 100%"
          >
            <el-option v-for="opt in voiceOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-space>
            <el-button type="primary" :icon="Check" :loading="saving" @click="handleSave">保存配置</el-button>
            <el-button :disabled="loading" @click="fetchConfig">刷新</el-button>
          </el-space>
        </el-form-item>
      </el-form>
      <div class="config-status">
        <div><strong>当前配置状态：</strong></div>
        <div>默认讯飞音色：<el-tag>{{ config.xfyun_voice || 'x4_yezi' }}</el-tag></div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, Check } from '@element-plus/icons-vue'
import api from '../api'

const loading = ref(false)
const saving = ref(false)
const formRef = ref(null)
const voiceOptions = ref([])
const config = reactive({
  xfyun_voice: 'x4_yezi',
})

const fetchVoiceOptions = async () => {
  try {
    const res = await api.get('/voice/voices')
    voiceOptions.value = res.data || []
  } catch (e) {
    console.error(e)
  }
}

const fetchConfig = async () => {
  loading.value = true
  try {
    const res = await api.get('/admin/settings/tts')
    Object.assign(config, res.data)
  } catch (e) {
    console.error(e)
    ElMessage.error('获取TTS配置失败')
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    await api.put('/admin/settings/tts', { ...config })
    ElMessage.success('配置已保存（需要重启后端服务才能生效）')
    await fetchConfig()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存配置失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchConfig()
  fetchVoiceOptions()
})
</script>

<style scoped>
.config-status {
  margin-top: 24px;
  padding: 16px;
  background: #f5f5f5;
  border-radius: 4px;
}
.config-status > div {
  margin-top: 8px;
}
.config-status > div:first-child {
  margin-top: 0;
}
.page-wrap {
  min-height: 200px;
}
.page-wrap .el-card {
  margin-top: 0;
}
</style>
