<template>
  <div id="app">
    <!-- 首页：不显示侧边导航，只显示主界面 -->
    <el-container v-if="isHome" class="layout">
      <el-header class="header">
        <div class="header-title">AI 数字人导游系统</div>
      </el-header>
      <el-main class="main main-with-header">
        <router-view :key="route.fullPath" />
      </el-main>
    </el-container>

    <!-- 其他页面：左侧固定导航 + 右侧内容区 -->
    <el-container v-else class="layout">
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

      <el-container class="content" :style="{ marginLeft: collapsed ? '64px' : '220px' }">
        <el-main
          class="main main-no-header"
          :class="{ 'main-no-scroll': route.path === '/voice-guide' }"
        >
          <router-view :key="route.fullPath" />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Microphone, Location, Document, Fold, Expand } from '@element-plus/icons-vue'

onMounted(() => {
  console.log('AI 数字人导游系统 - 游客端')
})

const collapsed = ref(false)
const route = useRoute()
const router = useRouter()

const activePath = computed(() => route.path)
const isHome = computed(() => route.path === '/')

const onSelect = (path) => {
  router.push(path)
}
</script>

<style>
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
</style>

