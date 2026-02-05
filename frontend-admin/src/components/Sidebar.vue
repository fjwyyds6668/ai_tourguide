<template>
  <el-aside
    :width="collapsed ? '64px' : '200px'"
    :class="['sidebar', { 'sidebar--collapsed': collapsed }]"
  >
    <div class="logo">
      <span class="logo-text">{{ collapsed ? 'AI' : 'AI 导游管理' }}</span>
    </div>
    <el-menu
      :default-active="$route.path"
      :collapse="collapsed"
      router
      class="sidebar-menu"
    >
      <el-menu-item index="/">
        <el-icon><Odometer /></el-icon>
        <span>仪表盘</span>
      </el-menu-item>
      <el-menu-item index="/characters">
        <el-icon><User /></el-icon>
        <span>角色管理</span>
      </el-menu-item>
      <el-menu-item index="/knowledge">
        <el-icon><Folder /></el-icon>
        <span>景区管理</span>
      </el-menu-item>
      <el-menu-item index="/analytics">
        <el-icon><DataAnalysis /></el-icon>
        <span>数据分析</span>
      </el-menu-item>
      <el-menu-item index="/settings">
        <el-icon><Setting /></el-icon>
        <span>系统设置</span>
      </el-menu-item>
    </el-menu>
    <div v-if="user" class="user-area">
      <el-dropdown trigger="click" placement="top-start" @command="handleCommand">
        <div class="user-trigger">
          <el-avatar :size="32" :src="user.avatar_url">
            <el-icon><UserFilled /></el-icon>
          </el-avatar>
          <span v-if="!collapsed" class="username">{{ user.username }}</span>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <div class="user-info">
                <div class="bold">{{ user.username }}</div>
                <div class="email">{{ user.email }}</div>
              </div>
            </el-dropdown-item>
            <el-dropdown-item command="upload">
              <el-icon><Upload /></el-icon> 上传头像
            </el-dropdown-item>
            <input
              ref="avatarInputRef"
              type="file"
              accept="image/*"
              style="display: none"
              @change="onAvatarFileChange"
            />
            <el-dropdown-item divided command="logout">
              <el-icon><SwitchButton /></el-icon>
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <div class="collapse-trigger" @click="$emit('toggle')">
      <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
    </div>
  </el-aside>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Odometer, User, Folder, DataAnalysis, Setting, UserFilled, Upload, SwitchButton, Fold, Expand } from '@element-plus/icons-vue'
import api from '../api'

defineProps({ collapsed: Boolean })
defineEmits(['toggle'])

const router = useRouter()
const user = ref(null)

onMounted(() => {
  const userStr = localStorage.getItem('user')
  user.value = userStr ? JSON.parse(userStr) : null
})

const avatarInputRef = ref(null)

const handleCommand = (cmd) => {
  if (cmd === 'logout') {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    router.push('/login')
  } else if (cmd === 'upload') {
    triggerAvatarInput()
  }
}

function triggerAvatarInput() {
  avatarInputRef.value?.click()
}

const beforeAvatarUpload = (file) => {
  const isImage = file.type?.startsWith('image/')
  if (!isImage) {
    ElMessage.error('只能上传图片文件')
    return false
  }
  const isLt5M = file.size / 1024 / 1024 < 5
  if (!isLt5M) {
    ElMessage.error('图片大小不能超过 5MB')
    return false
  }
  return true
}

const onAvatarFileChange = async (e) => {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file || !beforeAvatarUpload(file)) return
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/admin/profile/avatar', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const updatedUser = res.data?.user
    if (updatedUser) {
      localStorage.setItem('user', JSON.stringify(updatedUser))
      user.value = updatedUser
    }
    ElMessage.success('头像上传成功')
  } catch (err) {
    console.error(err)
    ElMessage.error(err.response?.data?.detail || '头像上传失败')
  }
}
</script>

<style scoped>
.sidebar {
  overflow: auto;
  height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  background: #fff;
  border-right: 1px solid #e5e7eb;
  transition: width 0.2s ease;
}
.logo {
  height: 56px;
  margin: 0 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid #f3f4f6;
}
.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: rgb(64, 158, 255);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sidebar-menu {
  border-right: none;
  padding: 8px 0;
}
.sidebar-menu .el-menu-item {
  border-radius: 8px;
  margin: 2px 8px;
  height: 44px;
}
.sidebar-menu .el-menu-item.is-active {
  background: rgba(64, 158, 255, 0.2);
  color: rgb(64, 158, 255);
}
.sidebar-menu .el-menu-item.is-active .el-icon {
  color: rgb(64, 158, 255);
}
/* 收缩时菜单项图标居中，与顶部 AI 一致 */
.sidebar--collapsed :deep(.sidebar-menu.el-menu--collapse .el-menu-item) {
  display: flex;
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
  margin-left: 8px;
  margin-right: 8px;
}
.sidebar--collapsed :deep(.sidebar-menu.el-menu--collapse .el-menu-item .el-icon) {
  margin-right: 0;
}
.user-area {
  position: absolute;
  bottom: 56px;
  left: 0;
  right: 0;
  padding: 0;
  z-index: 2;
  width: 100%;
  box-sizing: border-box;
}
.user-area :deep(.el-dropdown) {
  display: block !important;
  width: 100%;
}
.user-area :deep(.el-dropdown > *) {
  width: 100%;
  display: flex !important;
  justify-content: center;
  align-items: center;
}
.user-trigger {
  cursor: pointer;
  padding: 10px 12px;
  border-radius: 0;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  width: auto;
  min-width: 0;
  box-sizing: border-box;
  transition: background 0.2s;
}
.user-trigger:hover {
  background: #f3f4f6;
}
.user-trigger .el-avatar {
  flex-shrink: 0;
}
.username {
  flex: 0 1 auto;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  line-height: 32px;
  color: #374151;
  margin: 0;
  padding: 0;
}
.user-info .bold { font-weight: 600; color: #1f2937; }
.user-info .email { font-size: 12px; color: #6b7280; }
.collapse-trigger {
  position: absolute;
  bottom: 12px;
  left: 0;
  right: 0;
  text-align: center;
  cursor: pointer;
  color: #9ca3af;
  padding: 8px;
  border-radius: 6px;
  transition: color 0.2s, background 0.2s;
}
.collapse-trigger:hover {
  color: rgb(64, 158, 255);
  background: #f3f4f6;
}
</style>
