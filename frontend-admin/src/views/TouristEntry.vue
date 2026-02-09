<template>
  <div class="tourist-entry-page">
    <h1 class="admin-page-title">游客端入口</h1>
    <p class="page-desc">将下方二维码展示给游客，使用微信、QQ 或手机自带相机扫码即可打开游客端应用（可在浏览器或应用内打开）。</p>

    <el-card class="qrcode-card" shadow="hover">
      <div class="qrcode-area">
        <div v-if="displayUrl" class="qrcode-wrap">
          <img :src="qrcodeDataUrl" alt="游客端二维码" class="qrcode-img" />
          <p class="qrcode-tip">微信、QQ 或相机扫码均可打开</p>
        </div>
        <div v-else class="qrcode-placeholder">
          <el-icon :size="64" color="#c0c4cc"><PictureFilled /></el-icon>
          <p>请在下方的输入框中填写游客端访问地址</p>
        </div>
      </div>

      <el-divider />

      <div class="url-section">
        <label class="url-label">游客端地址</label>
        <el-input
          v-model="inputUrl"
          placeholder="例如：https://xxx.trycloudflare.com 或 http://192.168.1.100:5173"
          clearable
          class="url-input"
          @input="onUrlInput"
        />
        <p class="url-hint">
          <strong>所有人可扫码（无需同一 WiFi、无需隧道密码）</strong>：先启动游客端（<code>npm run dev</code>），在游客端目录执行 <code>npm run tunnel</code>（首次运行会自动下载隧道工具），将终端里显示的公网地址（如 https://xxx.trycloudflare.com）填入上方，即可生成二维码，游客扫码即开、无需输入密码。
        </p>
        <p class="url-hint url-hint-secondary">
          同一 WiFi 下也可用本机局域网 IP（如 http://192.168.x.x:5173）。若已在后端 .env 中配置 TOURIST_APP_URL，此处会自动带出。
        </p>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { PictureFilled } from '@element-plus/icons-vue'
import QRCode from 'qrcode'
import api from '../api'

const inputUrl = ref('')
const displayUrl = ref('')
const qrcodeDataUrl = ref('')

function normalizeUrl(url) {
  if (!url || typeof url !== 'string') return ''
  const s = url.trim()
  if (!s) return ''
  return s.startsWith('http://') || s.startsWith('https://') ? s : `http://${s}`
}

async function generateQr(url) {
  const u = normalizeUrl(url)
  if (!u) {
    qrcodeDataUrl.value = ''
    displayUrl.value = ''
    return
  }
  try {
    qrcodeDataUrl.value = await QRCode.toDataURL(u, { width: 280, margin: 2 })
    displayUrl.value = u
  } catch (e) {
    console.error(e)
    ElMessage.error('生成二维码失败')
    qrcodeDataUrl.value = ''
    displayUrl.value = ''
  }
}

function onUrlInput() {
  generateQr(inputUrl.value)
}

onMounted(async () => {
  try {
    const res = await api.get('/config/tourist-app-url')
    const url = res.data?.url
    if (url && url.trim()) {
      inputUrl.value = url.trim()
      await generateQr(url)
    }
  } catch (e) {
    console.error(e)
  }
})
</script>

<style scoped>
.tourist-entry-page {
  min-height: 200px;
}
.page-desc {
  color: #6b7280;
  font-size: 14px;
  margin-top: 4px;
  margin-bottom: 20px;
}
.qrcode-card {
  max-width: 480px;
}
.qrcode-area {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 320px;
}
.qrcode-wrap {
  text-align: center;
}
.qrcode-img {
  display: block;
  width: 280px;
  height: 280px;
  margin: 0 auto 12px;
}
.qrcode-tip {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
}
.qrcode-placeholder {
  text-align: center;
  color: #909399;
  font-size: 14px;
}
.qrcode-placeholder p {
  margin-top: 12px;
}
.url-section {
  margin-top: 8px;
}
.url-label {
  display: block;
  font-size: 14px;
  color: #303133;
  margin-bottom: 8px;
}
.url-input {
  max-width: 100%;
}
.url-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
  line-height: 1.6;
}
.url-hint code {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.url-hint-secondary {
  margin-top: 4px;
}
</style>
