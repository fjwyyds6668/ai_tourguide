<template>
  <div class="page-wrap">
    <h1 class="admin-page-title">景区管理</h1>
    <el-card class="content-card">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>景区管理</span>
          <el-space>
            <el-popconfirm title="确定要清空图数据库吗？此操作不可恢复！" confirm-button-text="确定" cancel-button-text="取消" @confirm="handleClearGraph">
              <template #reference>
                <el-button type="danger" :icon="Delete" :loading="loading">清空图数据库</el-button>
              </template>
            </el-popconfirm>
            <el-popconfirm title="确定要清空向量数据库吗？此操作不可恢复！" confirm-button-text="确定" cancel-button-text="取消" @confirm="handleClearVector">
              <template #reference>
                <el-button type="danger" :icon="Delete" :loading="loading">清空向量数据库</el-button>
              </template>
            </el-popconfirm>
            <el-button type="primary" :icon="Plus" @click="openScenicModal(null)">新增景区</el-button>
            <el-button :disabled="!selectedScenicId" @click="openScenicModal(selectedScenic)">编辑景区</el-button>
            <el-popconfirm title="确定要删除当前景区吗？" confirm-button-text="删除" cancel-button-text="取消" @confirm="deleteScenic(false)">
              <template #reference>
                <el-button type="danger" :disabled="!selectedScenicId">删除景区</el-button>
              </template>
            </el-popconfirm>
            <el-popconfirm title="确定要级联删除当前景区吗？会删除该景区下所有知识/景点" confirm-button-text="级联删除" cancel-button-text="取消" @confirm="deleteScenic(true)">
              <template #reference>
                <el-button type="danger" :disabled="!selectedScenicId">级联删除</el-button>
              </template>
            </el-popconfirm>
          </el-space>
        </div>
      </template>
      <div class="knowledge-layout">
        <div class="scenic-list">
          <div class="list-title">景区列表</div>
          <el-scrollbar max-height="400">
            <div
              v-for="item in scenicSpots"
              :key="item.id"
              class="scenic-item"
              :class="{ active: item.id === selectedScenicId }"
              @click="selectedScenicId = item.id"
            >
              <div class="scenic-name">{{ item.name }}</div>
              <div class="scenic-meta">知识 {{ item.knowledge_count }} / 景点 {{ item.attractions_count }}</div>
            </div>
          </el-scrollbar>
          <el-empty v-if="!scenicSpots.length && !loading" description="暂无景区，请点击「新增景区」添加" />
        </div>
        <div class="content-area">
          <div class="current-title">{{ selectedScenic ? `当前景区：${selectedScenic.name}` : '请选择景区' }}</div>
          <el-tabs>
            <el-tab-pane label="景区总知识">
              <div style="margin-bottom: 16px">
                <el-button type="primary" :icon="Plus" :disabled="!selectedScenicId" @click="openKnowledgeModal">添加知识</el-button>
              </div>
              <el-table :data="knowledgeData" v-loading="loading" row-key="text_id">
                <el-table-column prop="text_id" label="ID" width="140" />
                <el-table-column prop="text" label="内容" show-overflow-tooltip>
                  <template #default="{ row }">
                    <div class="text-cell">{{ row.text }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="100">
                  <template #default="{ row }">
                    <el-popconfirm title="确定要删除这条知识吗？" confirm-button-text="删除" cancel-button-text="取消" @confirm="deleteKnowledge(row)">
                      <template #reference>
                        <el-button type="danger" size="small">删除</el-button>
                      </template>
                    </el-popconfirm>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!knowledgeData.length && !loading" description="暂无知识，可点击「添加知识」上传" />
            </el-tab-pane>
            <el-tab-pane label="景点" :disabled="!selectedScenicId">
              <div style="margin-bottom: 16px">
                <el-button type="primary" :icon="Plus" @click="openAttractionModal">添加景点</el-button>
              </div>
              <el-table :data="attractionsData" v-loading="loading" row-key="id">
                <el-table-column prop="id" label="ID" width="80" />
                <el-table-column prop="name" label="名称" />
                <el-table-column label="操作" width="100">
                  <template #default="{ row }">
                    <el-popconfirm title="确定要删除这个景点吗？" @confirm="deleteAttraction(row)">
                      <template #reference>
                        <el-button type="danger" size="small">删除</el-button>
                      </template>
                    </el-popconfirm>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!attractionsData.length && !loading" description="暂无景点，可点击「添加景点」新增" />
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </el-card>

    <!-- 景区 新增/编辑 -->
    <el-dialog v-model="scenicVisible" :title="scenicEditing ? '编辑景区' : '新增景区'" width="560px" :close-on-click-modal="false" @closed="scenicFormRef?.resetFields()">
      <el-form ref="scenicFormRef" :model="scenicForm" label-position="top" @submit.prevent="submitScenic">
        <el-form-item label="景区名称" prop="name" required>
          <el-input v-model="scenicForm.name" placeholder="景区名称" />
        </el-form-item>
        <el-form-item label="位置" prop="location">
          <el-input v-model="scenicForm.location" placeholder="位置" />
        </el-form-item>
        <el-form-item label="简介" prop="description">
          <el-input v-model="scenicForm.description" type="textarea" :rows="3" placeholder="简介" />
        </el-form-item>
        <el-form-item label="封面图片" prop="cover_image_url">
          <el-input-group>
            <el-input v-model="scenicForm.cover_image_url" placeholder="上传后自动填入" readonly />
            <el-button :icon="Upload" @click="coverInputRef?.click()">上传</el-button>
          </el-input-group>
          <input ref="coverInputRef" type="file" accept="image/*" style="display: none" @change="onCoverUpload" />
        </el-form-item>
        <el-form-item v-if="!scenicEditing" label="景区知识（可选）" prop="knowledge_text">
          <el-input v-model="scenicForm.knowledge_text" type="textarea" :rows="5" placeholder="输入景区相关的知识内容..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scenicVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submitScenic">确定</el-button>
      </template>
    </el-dialog>

    <!-- 添加知识 -->
    <el-dialog v-model="knowledgeVisible" title="添加景区知识" width="560px" :close-on-click-modal="false" @closed="knowledgeFormRef?.resetFields()">
      <el-form ref="knowledgeFormRef" :model="knowledgeForm" :rules="knowledgeRules" label-position="top" @submit.prevent="submitKnowledge">
        <el-form-item label="知识ID" prop="text_id">
          <el-input v-model="knowledgeForm.text_id" placeholder="留空自动生成" />
        </el-form-item>
        <el-form-item label="知识内容" prop="text" required>
          <el-input v-model="knowledgeForm.text" type="textarea" :rows="6" placeholder="输入知识内容..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="knowledgeVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submitKnowledge">确定</el-button>
      </template>
    </el-dialog>

    <!-- 添加景点 -->
    <el-dialog v-model="attractionVisible" title="添加景点" width="560px" :close-on-click-modal="false" @closed="attractionFormRef?.resetFields()">
      <el-form ref="attractionFormRef" :model="attractionForm" :rules="attractionRules" label-position="top" @submit.prevent="submitAttraction">
        <el-form-item label="景点名称" prop="name" required>
          <el-input v-model="attractionForm.name" placeholder="景点名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description" required>
          <el-input v-model="attractionForm.description" type="textarea" :rows="4" placeholder="描述" />
        </el-form-item>
        <el-form-item label="景点图片（可选）" prop="image_url">
          <el-input-group>
            <el-input v-model="attractionForm.image_url" placeholder="上传后自动填入（可选）" readonly />
            <el-button :icon="Upload" @click="attractionImageRef?.click()">上传</el-button>
          </el-input-group>
          <input ref="attractionImageRef" type="file" accept="image/*" style="display: none" @change="onAttractionImageUpload" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="attractionVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submitAttraction">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete, Upload } from '@element-plus/icons-vue'
import api from '../api'

const loading = ref(false)
const scenicSpots = ref([])
const selectedScenicId = ref(null)
const scenicVisible = ref(false)
const scenicEditing = ref(null)
const scenicFormRef = ref(null)
const coverInputRef = ref(null)
const knowledgeVisible = ref(false)
const knowledgeFormRef = ref(null)
const knowledgeData = ref([])
const attractionsData = ref([])
const attractionVisible = ref(false)
const attractionFormRef = ref(null)
const attractionImageRef = ref(null)

const scenicForm = reactive({
  name: '',
  location: '',
  description: '',
  cover_image_url: '',
  knowledge_text: '',
})
const knowledgeForm = reactive({ text_id: '', text: '' })
const knowledgeRules = { text: [{ required: true, message: '请输入知识内容', trigger: 'blur' }] }
const attractionForm = reactive({ name: '', description: '', image_url: '' })
const attractionRules = {
  name: [{ required: true, message: '请输入景点名称', trigger: 'blur' }],
  description: [{ required: true, message: '请输入景点描述', trigger: 'blur' }],
}

const selectedScenic = computed(() => scenicSpots.value.find((s) => s.id === selectedScenicId.value) || null)

const loadScenicSpots = async (preferId = null) => {
  loading.value = true
  try {
    const res = await api.get('/admin/scenic-spots')
    const list = res.data || []
    scenicSpots.value = list
    const nextId =
      (preferId && list.find((x) => x.id === preferId)?.id) ||
      (selectedScenicId.value && list.find((x) => x.id === selectedScenicId.value)?.id) ||
      (list.length ? list[0].id : null)
    selectedScenicId.value = nextId
  } catch (e) {
    scenicSpots.value = []
  } finally {
    loading.value = false
  }
}

const loadScenicKnowledge = async (scenicId) => {
  if (!scenicId) return
  loading.value = true
  try {
    const res = await api.get(`/admin/scenic-spots/${scenicId}/knowledge`)
    knowledgeData.value = res.data || []
  } catch (e) {
    knowledgeData.value = []
  } finally {
    loading.value = false
  }
}

const loadScenicAttractions = async (scenicId) => {
  if (!scenicId) return
  loading.value = true
  try {
    const res = await api.get(`/admin/scenic-spots/${scenicId}/attractions`)
    attractionsData.value = res.data || []
  } catch (e) {
    attractionsData.value = []
  } finally {
    loading.value = false
  }
}

watch(selectedScenicId, (id) => {
  if (id) {
    loadScenicKnowledge(id)
    loadScenicAttractions(id)
  } else {
    knowledgeData.value = []
    attractionsData.value = []
  }
})

const handleClearGraph = async () => {
  loading.value = true
  try {
    await api.post('/admin/knowledge/clear-graph')
    ElMessage.success('已清空图数据库')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '清空失败')
  } finally {
    loading.value = false
  }
}

const handleClearVector = async () => {
  loading.value = true
  try {
    await api.post('/admin/knowledge/clear-vector')
    ElMessage.success('已清空向量数据库')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '清空失败')
  } finally {
    loading.value = false
  }
}

const openScenicModal = (edit) => {
  scenicEditing.value = edit || null
  if (edit) {
    Object.assign(scenicForm, {
      name: edit.name,
      location: edit.location,
      description: edit.description,
      cover_image_url: edit.cover_image_url,
      knowledge_text: '',
    })
  } else {
    Object.assign(scenicForm, { name: '', location: '', description: '', cover_image_url: '', knowledge_text: '' })
  }
  scenicVisible.value = true
}

const onCoverUpload = async (e) => {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await api.post('/admin/uploads/image', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    if (res.data?.image_url) scenicForm.cover_image_url = res.data.image_url
    ElMessage.success('封面图片上传成功')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '封面上传失败')
  }
}

const submitScenic = async () => {
  await scenicFormRef.value?.validate().catch(() => {})
  loading.value = true
  try {
    const { knowledge_text, ...rest } = scenicForm
    if (scenicEditing.value?.id) {
      await api.put(`/admin/scenic-spots/${scenicEditing.value.id}`, rest)
      ElMessage.success('更新成功')
      scenicVisible.value = false
      await loadScenicSpots(scenicEditing.value.id)
    } else {
      const res = await api.post('/admin/scenic-spots', rest)
      const newId = res.data?.id
      if (knowledge_text?.trim() && newId) {
        try {
          await api.post(
            `/admin/scenic-spots/${newId}/knowledge/upload`,
            [{ text: knowledge_text.trim(), text_id: `kb_${Date.now()}`, metadata: {} }],
            { timeout: 120000 }
          )
          ElMessage.success('景区和知识创建成功')
        } catch (err) {
          ElMessage.warning('景区创建成功，但知识上传失败：' + (err.response?.data?.detail || err.message))
        }
      } else {
        ElMessage.success('创建成功')
      }
      scenicVisible.value = false
      await loadScenicSpots(newId || null)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    loading.value = false
  }
}

const deleteScenic = async (cascade) => {
  if (!selectedScenicId.value) return
  loading.value = true
  try {
    await api.delete(`/admin/scenic-spots/${selectedScenicId.value}`, { params: { cascade } })
    ElMessage.success(cascade ? '已级联删除' : '删除成功')
    await loadScenicSpots(null)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  } finally {
    loading.value = false
  }
}

const openKnowledgeModal = () => {
  if (!selectedScenicId.value) {
    ElMessage.error('请先选择一个景区')
    return
  }
  knowledgeForm.text_id = ''
  knowledgeForm.text = ''
  knowledgeVisible.value = true
}

const submitKnowledge = async () => {
  await knowledgeFormRef.value?.validate().catch(() => {})
  if (!selectedScenicId.value) {
    ElMessage.error('请先选择一个景区')
    return
  }
  loading.value = true
  try {
    await api.post(
      `/admin/scenic-spots/${selectedScenicId.value}/knowledge/upload`,
      [{ text: knowledgeForm.text, text_id: knowledgeForm.text_id || `kb_${Date.now()}`, metadata: {} }],
      { timeout: 120000 }
    )
    ElMessage.success('上传成功')
    knowledgeVisible.value = false
    loadScenicKnowledge(selectedScenicId.value)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    loading.value = false
  }
}

const deleteKnowledge = async (row) => {
  loading.value = true
  try {
    await api.delete(`/admin/knowledge/${encodeURIComponent(row.text_id)}`)
    ElMessage.success('删除成功')
    loadScenicKnowledge(selectedScenicId.value)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  } finally {
    loading.value = false
  }
}

const openAttractionModal = () => {
  attractionForm.name = ''
  attractionForm.description = ''
  attractionForm.image_url = ''
  attractionVisible.value = true
}

const onAttractionImageUpload = async (e) => {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await api.post('/admin/uploads/image', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    if (res.data?.image_url) attractionForm.image_url = res.data.image_url
    ElMessage.success('景点图片上传成功')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '景点图片上传失败')
  }
}

const submitAttraction = async () => {
  await attractionFormRef.value?.validate().catch(() => {})
  if (!selectedScenicId.value) {
    ElMessage.error('请先选择一个景区')
    return
  }
  loading.value = true
  try {
    await api.post(`/admin/scenic-spots/${selectedScenicId.value}/attractions`, attractionForm)
    ElMessage.success('创建成功')
    attractionVisible.value = false
    loadScenicAttractions(selectedScenicId.value)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally {
    loading.value = false
  }
}

const deleteAttraction = async (row) => {
  loading.value = true
  try {
    await api.delete(`/admin/attractions/${row.id}`)
    ElMessage.success('删除成功')
    loadScenicAttractions(selectedScenicId.value)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadScenicSpots()
})
</script>

<style scoped>
.knowledge-layout {
  display: flex;
  gap: 16px;
}
.scenic-list {
  width: 320px;
}
.list-title {
  margin-bottom: 8px;
  font-weight: 600;
}
.scenic-item {
  padding: 12px;
  cursor: pointer;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  margin-bottom: 8px;
}
.scenic-item:hover,
.scenic-item.active {
  background: #f5f5f5;
}
.scenic-name {
  font-weight: 600;
}
.scenic-meta {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.content-area {
  flex: 1;
  min-width: 0;
}
.current-title {
  margin-bottom: 8px;
  font-weight: 600;
}
.text-cell {
  white-space: pre-wrap;
  word-break: break-word;
}
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
