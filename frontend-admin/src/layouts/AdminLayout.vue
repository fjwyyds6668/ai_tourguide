<template>
  <el-container class="admin-layout">
    <Sidebar :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    <el-container class="admin-main-wrap" :style="{ marginLeft: sidebarCollapsed ? '64px' : '200px' }">
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
  transition: margin-left 0.18s ease;
}
.admin-main-content {
  overflow: auto;
}
/* 仅透明度过渡，避免 transform 触发布局计算 */
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
