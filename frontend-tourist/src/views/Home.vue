<template>
  <div class="home">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>欢迎使用 AI 数字人导游系统</span>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="12">
          <el-card shadow="hover" @click="$router.push('/voice-guide')">
            <el-icon :size="48"><Microphone /></el-icon>
            <h3>语音导览</h3>
            <p>与 AI 导游进行实时语音交互</p>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover" @click="$router.push('/attractions')">
            <el-icon :size="48"><Location /></el-icon>
            <h3>景点浏览</h3>
            <p>查看所有景点信息</p>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { Microphone, Location } from '@element-plus/icons-vue'
</script>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.el-card {
  text-align: center;
  cursor: pointer;
  transition: transform 0.2s;
}

.el-card:hover {
  transform: translateY(-5px);
}

.el-icon {
  color: #409eff;
  margin-bottom: 10px;
}
</style>

