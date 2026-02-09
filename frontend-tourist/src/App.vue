<template>
  <div id="app">
    <!-- 首页：不显示侧边导航，只显示主界面 -->
    <el-container v-if="isHome" class="layout">
      <el-header class="header">
        <div class="header-title">AI 数字人导游系统</div>
      </el-header>
      <el-main class="main main-with-header">
        <router-view v-slot="{ Component }" :key="route.fullPath">
          <transition name="tourist-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>

    <!-- 其他页面：左侧固定导航 + 右侧内容区（桌面）；移动端为全屏内容 + 底部导航 -->
    <el-container v-else class="layout layout-inner">
      <el-aside class="aside" :width="collapsed ? '64px' : '220px'">
        <div class="brand" :class="{ collapsed }">
          <span class="brand-text">{{ collapsed ? 'AI' : 'AI 数字人导游系统' }}</span>
        </div>

        <el-menu
          class="menu"
          :default-active="activePath"
          :collapse="collapsed"
          :collapse-transition="false"
          @select="onSelect"
        >
          <el-menu-item index="/voice-guide">
            <el-icon><Microphone /></el-icon>
            <template #title>语音导览</template>
          </el-menu-item>
          <el-menu-item index="/attractions">
            <el-icon><Location /></el-icon>
            <template #title>景点浏览</template>
          </el-menu-item>
          <el-menu-item index="/history">
            <el-icon><Document /></el-icon>
            <template #title>历史记录</template>
          </el-menu-item>
        </el-menu>

        <div class="aside-footer" :class="{ collapsed }">
          <el-button text class="collapse-btn" @click="collapsed = !collapsed">
            <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
            <span v-if="!collapsed" style="margin-left: 6px;">收起</span>
          </el-button>
        </div>
      </el-aside>

      <el-container class="content" :style="contentMargin">
        <el-main
          class="main main-no-header"
          :class="{ 'main-no-scroll': route.path === '/voice-guide' }"
        >
          <router-view v-slot="{ Component }" :key="route.fullPath">
            <transition name="tourist-fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </el-main>
      </el-container>

      <!-- 移动端底部导航：仅在小屏显示 -->
      <nav class="bottom-nav" aria-label="主导航">
        <router-link to="/voice-guide" class="nav-item" :class="{ active: activePath === '/voice-guide' }">
          <el-icon><Microphone /></el-icon>
          <span>语音导览</span>
        </router-link>
        <router-link to="/attractions" class="nav-item" :class="{ active: activePath === '/attractions' }">
          <el-icon><Location /></el-icon>
          <span>景点浏览</span>
        </router-link>
        <router-link to="/history" class="nav-item" :class="{ active: activePath === '/history' }">
          <el-icon><Document /></el-icon>
          <span>历史记录</span>
        </router-link>
      </nav>
    </el-container>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Microphone, Location, Document, Fold, Expand } from '@element-plus/icons-vue'

const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1024)
const updateWidth = () => { windowWidth.value = window.innerWidth }
onMounted(() => {
  window.addEventListener('resize', updateWidth)
})
onUnmounted(() => {
  window.removeEventListener('resize', updateWidth)
})

const collapsed = ref(false)
const route = useRoute()
const router = useRouter()

const activePath = computed(() => route.path)
const isHome = computed(() => route.path === '/')

const contentMargin = computed(() => {
  if (windowWidth.value <= 768) return { marginLeft: '0' }
  return { marginLeft: collapsed.value ? '64px' : '220px' }
})

const onSelect = (path) => {
  router.push(path)
}
</script>

<style>
html {
  scroll-behavior: smooth;
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
}
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
}

#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #2c3e50;
  height: 100vh;
}

.layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.aside {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  background: #ffffff;
  border-right: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  z-index: 10;
  overflow: hidden; /* 让菜单区域自己滚动 */
}

.brand {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  background-color: #409eff;
  color: white;
  font-weight: 700;
}

.brand.collapsed {
  justify-content: center;
  padding: 0;
}

.brand-text {
  font-size: 16px;
  white-space: nowrap;
}

.menu {
  flex: 1;
  border-right: 0;
  overflow: auto;
  /* brand 56 + footer 48 = 104 */
  height: calc(100vh - 104px);
}
.menu .el-menu-item {
  transition: background-color 0.12s ease, color 0.12s ease;
}
@media (prefers-reduced-motion: reduce) {
  .menu .el-menu-item { transition: none; }
}

.aside-footer {
  height: 48px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-top: 1px solid #f0f0f0;
}

.aside-footer.collapsed {
  justify-content: center;
  padding: 0;
}

.collapse-btn {
  width: 100%;
  justify-content: flex-start;
}

.content {
  min-height: 100vh;
  position: relative;
}

/* 右侧顶栏固定，与左侧品牌栏同一顶边、同一高度 */
.content-header {
  position: fixed;
  top: 0;
  right: 0;
  height: 56px;
  z-index: 9;
  transition: left 0.2s;
}

.header {
  height: 56px;
  flex-shrink: 0;
  background-color: #409eff;
  color: white;
  display: flex;
  align-items: center;
  padding: 0 20px;
  box-sizing: border-box;
  position: relative;
  z-index: 100;
}

.header-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.main {
  overflow: auto;
  background: #f5f7fa;
}

.main.main-with-header {
  flex: 1;
  min-height: 0;
  height: calc(100vh - 56px);
}

.main.main-no-header {
  height: 100vh;
  margin-top: 0;
}

/* 只有语音导览页面关闭主区域滚动，其它页面正常滚动 */
.main-no-header.main-no-scroll {
  overflow: hidden;
}

/* 路由切换：仅透明度，缩短时间减轻卡顿 */
.tourist-fade-enter-active,
.tourist-fade-leave-active {
  transition: opacity 0.1s ease;
}
.tourist-fade-enter-from,
.tourist-fade-leave-to {
  opacity: 0;
}
@media (max-width: 768px) {
  .tourist-fade-enter-active,
  .tourist-fade-leave-active {
    transition-duration: 0.05s;
  }
}
@media (prefers-reduced-motion: reduce) {
  .tourist-fade-enter-active,
  .tourist-fade-leave-active { transition: none; }
}

/* ---------- 移动端自适应：小屏隐藏侧栏、内容全宽 + 底部导航 ---------- */
@media (max-width: 768px) {
  .layout-inner .aside {
    display: none;
  }
  .layout-inner .content {
    margin-left: 0 !important;
  }
  .layout-inner .main {
    padding-bottom: calc(56px + env(safe-area-inset-bottom, 0));
  }
  /* 移动端语音导览为上下堆叠，需允许滚动才能看到下方对话记录 */
  .main-no-header.main-no-scroll {
    overflow: auto !important;
    -webkit-overflow-scrolling: touch;
  }
  .bottom-nav {
    display: flex !important;
  }
}

.bottom-nav {
  display: none;
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: calc(56px + env(safe-area-inset-bottom, 0));
  padding-bottom: env(safe-area-inset-bottom, 0);
  background: #fff;
  border-top: 1px solid #eee;
  z-index: 100;
  align-items: center;
  justify-content: space-around;
  box-sizing: border-box;
}

.bottom-nav .nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 4px;
  color: #909399;
  text-decoration: none;
  font-size: 12px;
  gap: 4px;
  -webkit-tap-highlight-color: transparent;
}
.bottom-nav .nav-item .el-icon {
  font-size: 22px;
}
.bottom-nav .nav-item.active {
  color: #409eff;
  font-weight: 600;
}
</style>

