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
        修改配置后需要重启后端服务才能生效。默认使用在线科大讯飞 TTS；当启用备用TTS后，在线服务失败会自动降级到本地 CosyVoice2（也可选择强制始终使用 CosyVoice2）。
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
        <el-form-item label="启用备用TTS（本地 CosyVoice2）">
          <el-switch v-model="config.local_tts_enabled" />
        </el-form-item>
        <el-form-item label="强制使用备用TTS（CosyVoice2）">
          <el-switch v-model="config.local_tts_force" />
        </el-form-item>
        <el-form-item label="备用TTS引擎">
          <el-select v-model="config.local_tts_engine" disabled style="width: 100%">
            <el-option label="CosyVoice2" value="cosyvoice2" />
          </el-select>
        </el-form-item>
        <el-form-item label="CosyVoice2 模型路径（可选）">
          <el-input v-model="config.cosyvoice2_model_path" placeholder="例如：CosyVoice/models 或留空" clearable />
        </el-form-item>
        <el-form-item label="CosyVoice2 运行设备">
          <el-select v-model="config.cosyvoice2_device" style="width: 100%">
            <el-option label="cpu" value="cpu" />
            <el-option label="cuda" value="cuda" />
          </el-select>
        </el-form-item>
        <el-form-item label="CosyVoice2 语言">
          <el-select v-model="config.cosyvoice2_language" style="width: 100%">
            <el-option label="zh" value="zh" />
            <el-option label="en" value="en" />
            <el-option label="ja" value="ja" />
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
        <div>备用TTS（CosyVoice2）：<el-tag :type="config.local_tts_enabled ? 'success' : 'info'">{{ config.local_tts_enabled ? '已启用' : '未启用' }}</el-tag></div>
        <div>强制使用 CosyVoice2：<el-tag :type="config.local_tts_force ? 'warning' : 'info'">{{ config.local_tts_force ? '已启用' : '未启用' }}</el-tag></div>
        <div>备用引擎：<el-tag>{{ config.local_tts_engine || 'cosyvoice2' }}</el-tag></div>
        <div>CosyVoice2模型路径：<el-tag>{{ config.cosyvoice2_model_path || '未设置' }}</el-tag></div>
        <div>CosyVoice2设备：<el-tag>{{ config.cosyvoice2_device || 'cpu' }}</el-tag></div>
        <div>CosyVoice2语言：<el-tag>{{ config.cosyvoice2_language || 'zh' }}</el-tag></div>
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
  local_tts_enabled: false,
  local_tts_force: false,
  local_tts_engine: 'cosyvoice2',
  cosyvoice2_model_path: '',
  cosyvoice2_device: 'cpu',
  cosyvoice2_language: 'zh',
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
