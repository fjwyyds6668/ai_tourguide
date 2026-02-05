<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="always">
      <template #header>
        <div class="card-header">
          <span class="card-title">AI 导游系统</span>
          <span class="card-subtitle">管理员登录</span>
        </div>
      </template>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        @submit.prevent="onSubmit"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="onSubmit">
            登录
          </el-button>
        </el-form-item>
        <el-form-item>
          <div class="link-wrap">
            <el-button type="primary" link @click="$router.push('/register')">
              还没有账号？立即注册
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import api from '../api'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const onSubmit = async () => {
  await formRef.value?.validate().catch(() => {})
  try {
    loading.value = true
    const params = new URLSearchParams()
    params.append('username', form.username)
    params.append('password', form.password)
    const res = await api.post('/auth/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    const { access_token, user } = res.data
    localStorage.setItem('token', access_token)
    localStorage.setItem('user', JSON.stringify(user))
    ElMessage.success('登录成功')
    router.push('/')
  } catch (error) {
    const msg =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      '登录失败，请检查用户名和密码'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}
.login-card {
  width: 400px;
  border-radius: 12px;
  overflow: hidden;
  --el-fill-color-blank: #ffffff;
  --el-bg-color: #ffffff;
  --el-input-bg-color: #ffffff;
}
.login-card :deep(.el-card__header) {
  padding: 24px 24px 16px;
  border-bottom: 1px solid #f0f0f0;
}
.card-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.card-title {
  font-size: 22px;
  font-weight: 600;
  color: #1f2937;
}
.card-subtitle {
  font-size: 14px;
  color: #6b7280;
}
.link-wrap {
  width: 100%;
  text-align: center;
}
.login-card :deep(.el-input__wrapper) {
  border-radius: 8px;
  background: #ffffff !important;
  background-color: #ffffff !important;
  background-image: none !important;
  box-shadow: 0 0 0 1px #dcdfe6 inset !important;
}
.login-card :deep(.el-input__wrapper:hover),
.login-card :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #c0c4cc inset !important;
  background: #ffffff !important;
  background-color: #ffffff !important;
}
.login-card :deep(.el-input__inner),
.login-card :deep(.el-input input) {
  background: transparent !important;
  background-color: transparent !important;
}
.login-card :deep(.el-input input:-webkit-autofill),
.login-card :deep(.el-input input:-webkit-autofill:hover),
.login-card :deep(.el-input input:-webkit-autofill:focus) {
  box-shadow: 0 0 0 100px #ffffff inset !important;
  -webkit-text-fill-color: inherit !important;
}
.login-card :deep(.el-button--primary) {
  border-radius: 8px;
  height: 44px;
}
</style>
