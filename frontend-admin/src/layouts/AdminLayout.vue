<template>
  <el-container class="admin-layout">
    <Sidebar :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    <el-container class="admin-main-wrap" :class="{ 'admin-main-wrap--collapsed': sidebarCollapsed }">
      <el-main class="admin-main-content">
        <router-view v-slot="{ Component }">
          <transition name="admin-view" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref } from 'vue'
import Sidebar from '../components/Sidebar.vue'

const sidebarCollapsed = ref(false)
</script>

<style scoped>
.admin-layout {
  min-height: 100vh;
}
.admin-main-wrap {
  /* 布局始终按 200px 计算，避免收起时触发整页重排 */
  margin-left: 200px;
  will-change: transform;
  transform: translate3d(0, 0, 0);
  transition: transform 0.18s ease;
}
.admin-main-wrap--collapsed {
  /* 200px -> 64px 视觉效果，用 transform 合成层移动替代 margin-left 动画 */
  transform: translate3d(-136px, 0, 0);
}
.admin-main-content {
  overflow: auto;
}
.admin-main-content :deep(.admin-view-enter-active),
.admin-main-content :deep(.admin-view-leave-active) {
  transition: opacity 0.1s ease;
}
.admin-main-content :deep(.admin-view-enter-from),
.admin-main-content :deep(.admin-view-leave-to) {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .admin-main-wrap { transition: none; }
  .admin-main-content :deep(.admin-view-enter-active),
  .admin-main-content :deep(.admin-view-leave-active) { transition: none; }
}
</style>
