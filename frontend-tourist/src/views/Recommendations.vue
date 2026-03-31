<template>
  <div class="recommendations">
    <el-card class="page-card">
      <template #header>
        <span class="card-title">个性化推荐</span>
      </template>

      <div v-if="!sessionId" class="empty-hint">
        <el-icon :size="56" class="hint-icon"><ChatDotRound /></el-icon>
        <p class="hint-title">还没有对话记录</p>
        <p class="hint-desc">先去和 AI 导游聊聊，告诉它你的兴趣，再回来查看专属推荐</p>
        <el-button type="primary" @click="$router.push('/voice-guide')">去聊聊</el-button>
      </div>

      <div v-else-if="loading" class="loading-area">
        <el-icon class="loading-icon is-loading" :size="40"><Loading /></el-icon>
        <p>AI 正在分析你的对话，生成专属推荐…</p>
      </div>

      <div v-else-if="error" class="empty-hint">
        <p class="hint-desc">推荐生成失败，请稍后重试</p>
        <el-button @click="load">重试</el-button>
      </div>

      <div v-else-if="result">
        <div class="rec-text-card">
          <div class="rec-text-header">
            <el-icon><Promotion /></el-icon>
            <span>专属推荐</span>
          </div>
          <p class="rec-text">{{ result.recommendation }}</p>
        </div>

        <div v-if="result.attractions.length > 0" class="rec-grid">
          <el-card
            v-for="(item, index) in result.attractions"
            :key="item.id"
            shadow="hover"
            class="rec-card"
            @click="viewDetails(item)"
          >
            <div class="rank-badge" :class="rankClass(index)">{{ index + 1 }}</div>
            <div class="rec-img-wrap">
              <img
                v-if="item.image_url && !failedImages.has(item.id)"
                :src="imageSrc(item.image_url)"
                class="rec-img"
                alt=""
                loading="lazy"
                @error="failedImages.add(item.id)"
              />
              <div v-else class="rec-img-placeholder">
                <el-icon :size="40"><Picture /></el-icon>
              </div>
            </div>
            <div class="rec-info">
              <h3 class="rec-name">{{ item.name }}</h3>
              <p class="rec-desc">{{ item.description }}</p>
              <el-tag v-if="item.category" size="small">{{ item.category }}</el-tag>
            </div>
          </el-card>
        </div>

        <div class="refresh-row">
          <el-button type="primary" @click="load(true)">重新生成</el-button>
        </div>
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" title="景点详情" :width="dialogWidth">
      <div v-if="selected">
        <h3>{{ selected.name }}</h3>
        <p v-if="selected.location"><strong>位置：</strong>{{ selected.location }}</p>
        <div class="detail-img-wrap">
          <img v-if="selected.image_url" :src="imageSrc(selected.image_url)" class="detail-img" alt="" />
          <div v-else class="detail-img-placeholder"><el-icon :size="56"><Picture /></el-icon></div>
        </div>
        <p><strong>描述：</strong>{{ selected.description }}</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Picture, ChatDotRound, Loading, Promotion } from '@element-plus/icons-vue'
import api from '../api'

const SESSION_ID_KEY = 'vg_session_id'
const SESSION_CHAT_KEY = 'vg_chat_history'
const REC_CACHE_KEY = 'vg_rec_cache' // { result, chatLen, sessionId }

const sessionId = ref(null)
const result = ref(null)
const loading = ref(false)
const error = ref(false)
const failedImages = reactive(new Set())
const detailVisible = ref(false)
const selected = ref(null)
const _winW = ref(window.innerWidth)
const dialogWidth = computed(() => _winW.value <= 600 ? '92%' : '600px')

const getChatLen = () => {
  try {
    const raw = sessionStorage.getItem(SESSION_CHAT_KEY)
    if (!raw) return 0
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr.filter(m => m.role === 'user').length : 0
  } catch { return 0 }
}

const loadCache = () => {
  try {
    const raw = sessionStorage.getItem(REC_CACHE_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch { return null }
}

const saveCache = (res) => {
  try {
    sessionStorage.setItem(REC_CACHE_KEY, JSON.stringify({
      result: res,
      chatLen: getChatLen(),
      sessionId: sessionId.value,
    }))
  } catch {}
}

const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || 'http://localhost:18000'
const imageSrc = (url) => {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  if (url.startsWith('/')) return url
  return `${backendOrigin}${url}`
}

const rankClass = (index) => ['rank-gold', 'rank-silver', 'rank-bronze'][index] ?? 'rank-normal'

const viewDetails = async (item) => {
  selected.value = item
  detailVisible.value = true
  try {
    const res = await api.get(`/attractions/${item.id}`)
    if (res?.data) selected.value = res.data
  } catch (_) {}
}

const load = async (force = false) => {
  if (!sessionId.value) return

  if (!force) {
    const cache = loadCache()
    if (cache && cache.sessionId === sessionId.value && cache.chatLen === getChatLen() && cache.result) {
      result.value = cache.result
      return
    }
  }

  loading.value = true
  error.value = false
  result.value = null
  try {
    const scenicId = localStorage.getItem('current_scenic_spot_id')
    const params = { session_id: sessionId.value }
    if (scenicId) params.scenic_spot_id = Number(scenicId)
    const res = await api.get('/attractions/recommend', { params })
    if (res.data?.recommendation) {
      result.value = res.data
      saveCache(res.data)
    } else {
      error.value = true
    }
  } catch (_) {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  sessionId.value = sessionStorage.getItem(SESSION_ID_KEY) || null
  if (sessionId.value) load()
})
</script>

<style scoped>
.recommendations {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.page-card {
  --el-card-bg-color: rgba(255, 255, 255, 0.45);
  border-radius: 12px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.60) !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
}
.page-card :deep(.el-card__body) { background: transparent !important; }
.page-card :deep(.el-card__header) {
  padding: 14px 20px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.35);
  background: transparent !important;
}
.card-title { font-size: 16px; color: #1a1a1a; font-weight: 700; }

.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 20px;
  gap: 12px;
  text-align: center;
}
.hint-icon { color: #c0c4cc; }
.hint-title { font-size: 16px; font-weight: 600; color: #303133; margin: 0; }
.hint-desc { font-size: 14px; color: #909399; margin: 0; }

.loading-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 20px;
  gap: 16px;
  color: #606266;
  font-size: 14px;
}
.loading-icon { color: #409eff; }

.rec-text-card {
  background: rgba(64, 158, 255, 0.08);
  border: 1px solid rgba(64, 158, 255, 0.25);
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 24px;
}
.rec-text-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 10px;
}
.rec-text {
  font-size: 14px;
  color: #303133;
  line-height: 1.8;
  margin: 0;
  white-space: pre-wrap;
}

.rec-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
  margin-bottom: 16px;
}

.rec-card {
  --el-card-bg-color: rgba(255, 255, 255, 0.72);
  border-radius: 10px;
  cursor: pointer;
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.55) !important;
  transition: transform 0.12s, box-shadow 0.12s;
}
.rec-card:hover { transform: translateY(-3px); box-shadow: 0 10px 28px rgba(0,0,0,0.15); }
.rec-card :deep(.el-card__body) { background: transparent !important; padding: 0; }

.rank-badge {
  position: absolute; top: 10px; left: 10px; z-index: 2;
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; color: #fff;
}
.rank-gold   { background: #f5a623; }
.rank-silver { background: #9b9b9b; }
.rank-bronze { background: #c47c3a; }
.rank-normal { background: rgba(0,0,0,0.35); }

.rec-img-wrap {
  width: 100%; aspect-ratio: 16/9; overflow: hidden;
  border-radius: 10px 10px 0 0;
  background: rgba(200,200,200,0.15);
}
.rec-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.rec-img-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center; color: #c0c4cc;
}

.rec-info { padding: 12px; }
.rec-name { margin: 0 0 6px; font-size: 15px; font-weight: 600; }
.rec-desc {
  font-size: 13px; color: #606266; margin: 0 0 8px;
  overflow: hidden; text-overflow: ellipsis;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}

.refresh-row { text-align: center; padding-top: 8px; }

.detail-img-wrap { margin: 12px 0 10px; }
.detail-img { width: 100%; max-height: 320px; object-fit: cover; border-radius: 10px; display: block; }
.detail-img-placeholder {
  width: 100%; height: 260px;
  display: flex; align-items: center; justify-content: center;
  background: #f5f7fa; border-radius: 10px; color: #9aa0a6;
}

@media (max-width: 768px) {
  .recommendations { padding: 12px; }
  .rec-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
}
</style>
