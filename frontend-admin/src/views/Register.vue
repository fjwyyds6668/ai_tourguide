<template>
  <div class="register-wrap">
    <el-card class="register-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="card-title">AI 导游系统</span>
          <span class="card-subtitle">管理员注册</span>
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
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="email">
          <el-input v-model="form.email" placeholder="邮箱" :prefix-icon="Message" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password :prefix-icon="Lock" />
        </el-form-item>
        <el-form-item prop="confirm">
          <el-input v-model="form.confirm" type="password" placeholder="确认密码" show-password :prefix-icon="Lock" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="onSubmit">
            注册
          </el-button>
        </el-form-item>
        <el-form-item>
          <div class="link-wrap">
            <el-button type="primary" link @click="$router.push('/login')">
              已有账号？立即登录
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
import { User, Lock, Message } from '@element-plus/icons-vue'
import api from '../api'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)
const form = reactive({ username: '', email: '', password: '', confirm: '' })
const validateConfirm = (_rule, value, callback) => {
  if (value !== form.password) callback(new Error('两次输入的密码不一致'))
  else callback()
}
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名至少3个字符', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6个字符', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

const onSubmit = async () => {
  await formRef.value?.validate().catch(() => {})
  try {
    loading.value = true
    await api.post('/auth/register', {
      username: form.username,
      email: form.email,
      password: form.password,
    })
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '注册失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, oklab(62.707% 0.0044 -0.16387) 0%, #764ba2 100%);
  padding: 20px;
}
.register-card {
  width: 400px;
  border-radius: 12px;
  overflow: hidden;
  --el-fill-color-blank: #ffffff;
  --el-bg-color: #ffffff;
  --el-input-bg-color: #ffffff;
}
.register-card :deep(.el-card__header) {
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
.register-card :deep(.el-input__wrapper) {
  border-radius: 8px;
  background: #ffffff !important;
  background-color: #ffffff !important;
  background-image: none !important;
  box-shadow: 0 0 0 1px #dcdfe6 inset !important;
}
.register-card :deep(.el-input__wrapper:hover),
.register-card :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #c0c4cc inset !important;
  background: #ffffff !important;
  background-color: #ffffff !important;
}
.register-card :deep(.el-input__inner),
.register-card :deep(.el-input input) {
  background: transparent !important;
  background-color: transparent !important;
}
.register-card :deep(.el-input input:-webkit-autofill),
.register-card :deep(.el-input input:-webkit-autofill:hover),
.register-card :deep(.el-input input:-webkit-autofill:focus) {
  box-shadow: 0 0 0 100px #ffffff inset !important;
  -webkit-text-fill-color: inherit !important;
}
.register-card :deep(.el-button--primary) {
  border-radius: 8px;
  height: 44px;
}
</style>
