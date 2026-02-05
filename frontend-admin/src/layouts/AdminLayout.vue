<template>
  <el-container class="admin-layout">
    <Sidebar :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    <el-container class="admin-main-wrap" :style="{ marginLeft: sidebarCollapsed ? '64px' : '200px' }">
      <el-main class="admin-main-content">
        <router-view />
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
  transition: margin-left 0.2s ease;
}
.admin-main-content {
  overflow: auto;
}
</style>
