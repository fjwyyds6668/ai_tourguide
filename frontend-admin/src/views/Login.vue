<template>
  <div class="page">
    <div class="main">

      <div class="container a-container" :class="{ 'is-txl': isLogin, 'is-fadeout': isFading }">
        <form class="form" @submit.prevent="onRegister">
          <h2 class="form_title title">创建账号</h2>
          <span class="form__span">使用邮箱注册管理账号</span>
          <div class="field-wrap">
            <input class="form__input" type="text" placeholder=" " v-model="regForm.username" autocomplete="username">
            <label class="field-label">用户名（≥3位）</label>
          </div>
          <p v-if="regErrors.username" class="form__err">{{ regErrors.username }}</p>
          <div class="field-wrap">
            <input class="form__input" type="email" placeholder=" " v-model="regForm.email" autocomplete="email">
            <label class="field-label">邮箱地址</label>
          </div>
          <p v-if="regErrors.email" class="form__err">{{ regErrors.email }}</p>
          <div class="field-wrap has-eye">
            <input class="form__input" :type="showRegPwd ? 'text' : 'password'" placeholder=" " v-model="regForm.password" autocomplete="new-password">
            <label class="field-label">密码（≥6位）</label>
            <button type="button" class="eye-btn" @click="showRegPwd = !showRegPwd" tabindex="-1">
              <svg v-if="!showRegPwd" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            </button>
          </div>
          <p v-if="regErrors.password" class="form__err">{{ regErrors.password }}</p>
          <button class="form__button button" type="submit" :disabled="regLoading">
            <span v-if="!regLoading">注&ensp;册</span>
            <span v-else class="btn-dots"><i v-for="n in 3" :key="n" :style="{animationDelay:(n-1)*.2+'s'}"></i></span>
          </button>
        </form>
      </div>

      <div class="container b-container" :class="{ 'is-txl': isLogin, 'is-z200': isZ200 }">
        <form class="form" @submit.prevent="onLogin">
          <h2 class="form_title title">欢迎登录</h2>
          <span class="form__span">使用管理员账号登录系统</span>
          <div class="field-wrap">
            <input class="form__input" type="text" placeholder=" " v-model="loginForm.username" autocomplete="off">
            <label class="field-label">用户名</label>
          </div>
          <p v-if="loginErrors.username" class="form__err">{{ loginErrors.username }}</p>
          <div class="field-wrap has-eye">
            <input class="form__input" :type="showLoginPwd ? 'text' : 'password'" placeholder=" " v-model="loginForm.password" autocomplete="new-password">
            <label class="field-label">密码</label>
            <button type="button" class="eye-btn" @click="showLoginPwd = !showLoginPwd" tabindex="-1">
              <svg v-if="!showLoginPwd" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            </button>
          </div>
          <p v-if="loginErrors.password" class="form__err">{{ loginErrors.password }}</p>
<button class="form__button button" type="submit" :disabled="loginLoading">
            <span v-if="!loginLoading">登&ensp;录</span>
            <span v-else class="btn-dots"><i v-for="n in 3" :key="n" :style="{animationDelay:(n-1)*.2+'s'}"></i></span>
          </button>
        </form>
      </div>

      <div class="switch" :class="{ 'is-txr': isLogin, 'is-gx': animating }">
        <div class="switch__circle" :class="{ 'is-txr': isLogin }"></div>
        <div class="switch__circle switch__circle--t" :class="{ 'is-txr': isLogin }"></div>

        <div class="switch__container" :class="{ 'is-hidden': isLogin }">
          <h2 class="switch__title title">欢迎回来！</h2>
          <p class="switch__description description">已有账号？请直接登录AI数字人导游系统</p>
          <button class="switch__button button" @click.prevent="changeForm">登&ensp;录</button>
        </div>

        <div class="switch__container" :class="{ 'is-hidden': !isLogin }">
          <h2 class="switch__title title">你好，朋友！</h2>
          <p class="switch__description description">填写个人信息，开启智能导游管理之旅</p>
          <button class="switch__button button" @click.prevent="changeForm">注&ensp;册</button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const router = useRouter()

const showLoginPwd = ref(false)
const showRegPwd   = ref(false)


const isLogin   = ref(false)
const isZ200    = ref(false)
const isFading  = ref(false)
const animating = ref(false)
const changeForm = () => {
  animating.value = true
  setTimeout(() => { animating.value = false }, 1500)
  if (!isLogin.value) {
    isFading.value = true
    isZ200.value   = true
    isLogin.value  = true
  } else {
    isZ200.value   = false
    isFading.value = false
    isLogin.value  = false
  }
}

const loginLoading = ref(false)
const loginForm    = reactive({ username: '', password: '' })
const loginErrors  = reactive({ username: '', password: '' })
const validateLogin = () => {
  loginErrors.username = loginForm.username.trim() ? '' : '请输入用户名'
  loginErrors.password = loginForm.password        ? '' : '请输入密码'
  return !loginErrors.username && !loginErrors.password
}
const onLogin = async () => {
  if (!validateLogin()) return
  try {
    loginLoading.value = true
    const params = new URLSearchParams()
    params.append('username', loginForm.username)
    params.append('password', loginForm.password)
    const res = await api.post('/auth/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    const { access_token, user } = res.data
    if (!user?.is_admin) {
      ElMessage.error('该账号不是管理员，无法登录管理端')
      return
    }
    localStorage.setItem('token', access_token)
    localStorage.setItem('user', JSON.stringify(user))
    ElMessage.success('登录成功')
    router.push('/')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || err.message || '登录失败')
  } finally {
    loginLoading.value = false
  }
}

const regLoading = ref(false)
const regForm    = reactive({ username: '', email: '', password: '' })
const regErrors  = reactive({ username: '', email: '', password: '' })
const validateReg = () => {
  regErrors.username = regForm.username.trim().length >= 3 ? '' : '用户名至少3个字符'
  regErrors.email    = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(regForm.email) ? '' : '请输入有效邮箱'
  regErrors.password = regForm.password.length >= 6 ? '' : '密码至少6个字符'
  return !regErrors.username && !regErrors.email && !regErrors.password
}
const onRegister = async () => {
  if (!validateReg()) return
  try {
    regLoading.value = true
    await api.post('/auth/register', {
      username: regForm.username,
      email: regForm.email,
      password: regForm.password,
    })
    ElMessage.success('注册成功，请登录')
    changeForm()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '注册失败，请重试')
  } finally {
    regLoading.value = false
  }
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700;800&display=swap');

*, *::after, *::before { margin:0; padding:0; box-sizing:border-box; user-select:none; }

.page {
  width: 100%;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  font-family: 'Montserrat', 'Microsoft YaHei', sans-serif;
  font-size: 12px;
  background-color: #ecf0f3;
  color: #a0a5a8;
}

.main {
  position: relative;
  width: 1000px; min-width: 1000px;
  height: 600px; min-height: 600px;
  padding: 25px;
  background-color: #ecf0f3;
  box-shadow: 10px 10px 10px #d1d9e6, -10px -10px 10px #f9f9f9;
  border-radius: 12px;
  overflow: hidden;
}
@media (max-width: 1200px) { .main { transform: scale(.7); } }
@media (max-width: 1000px) { .main { transform: scale(.6); } }
@media (max-width: 800px)  { .main { transform: scale(.5); } }
@media (max-width: 600px)  { .main { transform: scale(.4); } }

.container {
  display: flex;
  justify-content: center;
  align-items: center;
  position: absolute;
  top: 0;
  width: 600px;
  height: 100%;
  padding: 25px;
  background-color: #ecf0f3;
  transition: transform 1.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.5s ease;
  will-change: transform;
}
.a-container { z-index: 100; left: calc(100% - 600px); }
.b-container { left: calc(100% - 600px); z-index: 0; opacity: 0; }
.b-container.is-z200 { z-index: 200; opacity: 1; }

.form {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.title {
  font-size: 34px;
  font-weight: 700;
  line-height: 3;
  color: #181818;
}
.description {
  font-size: 14px;
  letter-spacing: .25px;
  text-align: center;
  line-height: 1.6;
}

.form__span { margin-top: 30px; margin-bottom: 12px; font-size: 12px; }

.form__input {
  width: 350px;
  height: 40px;
  margin: 4px 0;
  padding-left: 25px;
  font-size: 13px;
  letter-spacing: .15px;
  border: none;
  outline: none;
  font-family: 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, sans-serif;
  background-color: #ecf0f3;
  color: #181818;
  transition: .25s ease;
  border-radius: 8px;
  box-shadow: inset 2px 2px 4px #d1d9e6, inset -2px -2px 4px #f9f9f9;
}
.form__input:focus {
  box-shadow: inset 4px 4px 4px #d1d9e6, inset -4px -4px 4px #f9f9f9;
}
.form__input::placeholder { color: transparent; }
.form__input:-webkit-autofill,
.form__input:-webkit-autofill:focus {
  -webkit-box-shadow: inset 2px 2px 4px #d1d9e6, inset -2px -2px 4px #f9f9f9, 0 0 0 100px #ecf0f3 inset !important;
  -webkit-text-fill-color: #181818 !important;
}

.field-wrap {
  position: relative;
  width: 350px;
  margin: 10px 0 4px;
}
.field-wrap .form__input {
  width: 100%;
  margin: 0;
}
.field-label {
  position: absolute;
  left: 18px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 13px;
  color: #a0a5a8;
  pointer-events: none;
  transition: top .2s ease, font-size .2s ease, color .2s ease;
  background: transparent;
  padding: 0 4px;
  white-space: nowrap;
}
.form__input:focus ~ .field-label,
.form__input:not(:placeholder-shown) ~ .field-label,
.form__input:-webkit-autofill ~ .field-label {
  top: 0;
  font-size: 11px;
  color: #4B70E2;
  background: #ecf0f3;
}
.field-wrap.has-eye .form__input { padding-right: 44px; }
.eye-btn {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  outline: none;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  color: #a0a5a8;
  transition: color .2s;
  margin-top: 0;
  width: auto;
  height: auto;
  border-radius: 0;
  box-shadow: none;
  font-size: 0;
  letter-spacing: 0;
}
.eye-btn:hover { color: #4B70E2; }
.eye-btn svg { width: 18px; height: 18px; display: block; }

.form__err {
  font-size: 11px;
  color: #e05c5c;
  margin: 2px 0;
  width: 350px;
  padding-left: 4px;
  text-align: left;
}

.form__link {
  color: #181818;
  font-size: 15px;
  margin-top: 25px;
  border-bottom: 1px solid #a0a5a8;
  line-height: 2;
  cursor: pointer;
  transition: .2s;
  text-decoration: none;
}
.form__link:hover { color: #4B70E2; border-color: #4B70E2; }

.button {
  width: 180px;
  height: 50px;
  border-radius: 25px;
  margin-top: 40px;
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 1.15px;
  font-family: 'Montserrat', 'Microsoft YaHei', sans-serif;
  background-color: #4B70E2;
  color: #f9f9f9;
  box-shadow: 8px 8px 16px #d1d9e6, -8px -8px 16px #f9f9f9;
  border: none;
  outline: none;
  cursor: pointer;
  transition: .25s;
}
.button:hover:not(:disabled) {
  box-shadow: 6px 6px 10px #d1d9e6, -6px -6px 10px #f9f9f9;
  transform: scale(.985);
}
.button:active:not(:disabled) {
  box-shadow: 2px 2px 6px #d1d9e6, -2px -2px 6px #f9f9f9;
  transform: scale(.97);
}
.button:disabled { opacity: .65; cursor: not-allowed; }

.btn-dots { display: inline-flex; align-items: center; gap: 4px; }
.btn-dots i {
  display: inline-block;
  width: 5px; height: 5px;
  border-radius: 50%;
  background: #f9f9f9;
  animation: dotUp .6s ease-in-out infinite alternate;
}
@keyframes dotUp {
  from { transform: translateY(0); opacity: .4; }
  to   { transform: translateY(-4px); opacity: 1; }
}

.switch {
  display: flex;
  justify-content: center;
  align-items: center;
  position: absolute;
  top: 0; left: 0;
  height: 100%;
  width: 400px;
  padding: 50px;
  z-index: 200;
  transition: transform 1.25s cubic-bezier(0.4, 0, 0.2, 1), width 1.25s cubic-bezier(0.4, 0, 0.2, 1);
  will-change: transform;
  background-color: #ecf0f3;
  overflow: hidden;
  box-shadow: 4px 4px 10px #d1d9e6, -4px -4px 10px #f9f9f9;
}

.switch__circle {
  position: absolute;
  width: 500px; height: 500px;
  border-radius: 50%;
  background-color: #ecf0f3;
  box-shadow: inset 8px 8px 12px #d1d9e6, inset -8px -8px 12px #f9f9f9;
  bottom: -60%; left: -60%;
  transition: 1.25s;
}
.switch__circle--t {
  top: -30%; left: 60%;
  width: 300px; height: 300px;
  bottom: unset;
}

.switch__container {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  position: absolute;
  width: 400px;
  padding: 50px 55px;
  transition: 1.25s;
}

.switch.is-txr    { left: 0; transform: translateX(600px); }
.container.is-txl { left: calc(100% - 600px); transform: translateX(-400px); }
.is-txr { left: calc(100% - 400px); }
.is-txl { left: 0; }
.a-container.is-fadeout { opacity: 0; }
.is-z200 { z-index: 200; }
.is-hidden { visibility: hidden; opacity: 0; position: absolute; transition: opacity 1.25s, visibility 1.25s; }
.is-gx { animation: is-gx 1.25s cubic-bezier(0.4, 0, 0.2, 1); }
@keyframes is-gx {
  0%, 10%, 100% { width: 400px; }
  30%, 50%      { width: 500px; }
}
</style>
