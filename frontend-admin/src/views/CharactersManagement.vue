<template>
  <div class="page-wrap">
    <h1 class="admin-page-title">数字人角色管理</h1>
    <el-card class="content-card">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>角色列表</span>
          <el-space>
            <el-button :icon="Refresh" @click="fetchList">刷新</el-button>
            <el-button type="primary" :icon="Plus" @click="openCreate">新增角色</el-button>
          </el-space>
        </div>
      </template>
      <el-table :data="rows" v-loading="loading" row-key="id" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="名称" min-width="140">
          <template #default="{ row }">
            <div>
              <strong>{{ row.name }}</strong>
              <el-tag v-if="row.style" size="small" type="info" style="margin-left: 8px">{{ row.style }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="数字人配置" width="200">
          <template #default="{ row }">
            <div>
              <span v-if="!row.live2d_character_name" style="color: #999">-</span>
              <el-tag v-else type="info">{{ digitalHumanLabel(row.live2d_character_name) }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="avatar_url" label="头像/模型ID" min-width="120" show-overflow-tooltip />
        <el-table-column label="语音" width="200">
          <template #default="{ row }">
            <div>
              <span v-if="!row.voice" style="color: #999">默认</span>
              <el-tag v-else type="success" size="small">{{ voiceLabel(row.voice) }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="100">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" @change="(v) => handleToggleActive(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-space>
              <el-button size="small" :icon="Edit" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" type="danger" :icon="Delete" @click="handleDelete(row)">删除</el-button>
            </el-space>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="modalOpen"
      :title="editing ? '编辑角色' : '新增角色'"
      width="640px"
      :close-on-click-modal="false"
      destroy-on-close
      @closed="formRef?.resetFields()"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：亲切导游 / 专业学者" />
        </el-form-item>
        <el-form-item label="讲解风格" prop="style">
          <el-input v-model="form.style" placeholder="例如：亲切导游" />
        </el-form-item>
        <el-form-item label="头像/模型ID" prop="avatar_url">
          <el-input-group>
            <el-input v-model="form.avatar_url" placeholder="可填模型ID或通过右侧上传图片" />
            <el-button :icon="Upload" @click="triggerAvatarUpload">上传</el-button>
          </el-input-group>
          <input ref="avatarUploadRef" type="file" accept="image/*" style="display: none" @change="onAvatarUpload" />
        </el-form-item>
        <el-form-item label="简介" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="角色简介" />
        </el-form-item>
        <el-form-item label="角色提示词" prop="prompt" required>
          <el-input v-model="form.prompt" type="textarea" :rows="10" placeholder="用于控制角色说话风格、口吻、身份设定等" />
        </el-form-item>
        <el-form-item label="语音选择" prop="voice">
          <el-select v-model="form.voice" placeholder="选择讯飞音色（可选）" clearable filterable style="width: 100%">
            <el-option v-for="opt in voiceOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="数字人形象选择" prop="live2d_character_name">
          <el-select v-model="form.live2d_character_name" placeholder="选择数字人形象（可选）" clearable filterable style="width: 100%">
            <el-option v-for="opt in DIGITAL_HUMAN_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="是否启用" prop="is_active">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modalOpen = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, Refresh, Upload } from '@element-plus/icons-vue'
import api from '../api'

const DIGITAL_HUMAN_OPTIONS = [
  { value: 'Mao', label: '艺术家风格（默认）' },
  { value: 'Chitose', label: '温柔风格' },
  { value: 'Tsumiki', label: '可爱风格' },
  { value: 'Hibiki', label: '活泼风格' },
  { value: 'Izumi', label: '成熟风格' },
  { value: 'Hiyori', label: '标准风格' },
  { value: 'Haru', label: '友好风格' },
  { value: 'Epsilon', label: '优雅风格' },
  { value: 'Shizuku', label: '文静风格' },
  { value: 'Kei', label: '专业风格（多语言）' },
]

const emptyToNull = (v) => (v === '' ? null : v)
const loading = ref(false)
const submitting = ref(false)
const rows = ref([])
const modalOpen = ref(false)
const editing = ref(null)
const formRef = ref(null)
const avatarUploadRef = ref(null)
const voiceOptions = ref([])

const form = reactive({
  name: '',
  style: '',
  avatar_url: '',
  description: '',
  prompt: '',
  voice: null,
  live2d_character_name: null,
  is_active: true,
})
const formRules = {
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  prompt: [{ required: true, message: '请输入角色提示词', trigger: 'blur' }],
}

const digitalHumanLabel = (v) => DIGITAL_HUMAN_OPTIONS.find((o) => o.value === v)?.label ?? v
const voiceLabel = (v) => voiceOptions.value.find((o) => o.value === v)?.label ?? v

const fetchVoiceOptions = async () => {
  try {
    const res = await api.get('/voice/voices')
    voiceOptions.value = res.data || []
  } catch (e) {
    console.error(e)
  }
}

const fetchList = async () => {
  loading.value = true
  try {
    const res = await api.get('/characters/characters', { params: { active_only: false } })
    rows.value = res.data || []
  } catch (e) {
    console.error(e)
    ElMessage.error(e.response?.data?.detail || '获取角色列表失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editing.value = null
  Object.assign(form, {
    name: '',
    style: '',
    avatar_url: '',
    description: '',
    prompt: '',
    voice: null,
    live2d_character_name: null,
    is_active: true,
  })
  modalOpen.value = true
}

const openEdit = (row) => {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    style: row.style ?? '',
    avatar_url: row.avatar_url ?? '',
    description: row.description ?? '',
    prompt: row.prompt ?? '',
    voice: row.voice ?? null,
    live2d_character_name: row.live2d_character_name ?? null,
    is_active: !!row.is_active,
  })
  modalOpen.value = true
}

const handleDelete = (row) => {
  ElMessageBox.confirm(`删除角色「${row.name}」？删除后不可恢复。`, '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      await api.delete(`/characters/characters/${row.id}`)
      ElMessage.success('删除成功')
      fetchList()
    })
    .catch(() => {})
}

const handleToggleActive = async (row, checked) => {
  try {
    await api.put(`/characters/characters/${row.id}`, { is_active: checked })
    ElMessage.success('更新成功')
    fetchList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  }
}

const triggerAvatarUpload = () => avatarUploadRef.value?.click()
const onAvatarUpload = async (e) => {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await api.post('/admin/uploads/image', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    const url = res.data?.image_url
    if (url) form.avatar_url = url
    ElMessage.success('头像图片上传成功')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '头像上传失败')
  }
}

const handleSubmit = async () => {
  await formRef.value?.validate().catch(() => {})
  submitting.value = true
  try {
    const payload = {
      name: form.name,
      style: emptyToNull(form.style?.trim() ?? ''),
      avatar_url: emptyToNull(form.avatar_url?.trim() ?? ''),
      description: emptyToNull(form.description?.trim() ?? ''),
      prompt: emptyToNull(form.prompt?.trim() ?? ''),
      voice: emptyToNull(form.voice),
      live2d_character_name: emptyToNull(form.live2d_character_name),
      live2d_character_group: 'free',
      is_active: !!form.is_active,
    }
    if (editing.value) {
      await api.put(`/characters/characters/${editing.value.id}`, payload)
      ElMessage.success('更新成功')
    } else {
      await api.post('/characters/characters', payload)
      ElMessage.success('创建成功')
    }
    modalOpen.value = false
    fetchList()
  } catch (e) {
    if (e?.errors) return
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchList()
  fetchVoiceOptions()
})
</script>

<style scoped>
.page-wrap {
  min-height: 200px;
}
.content-card {
  margin-top: 0;
}
.content-card :deep(.el-card__header) {
  padding: 16px 20px;
  font-weight: 500;
  color: #374151;
}
</style>
