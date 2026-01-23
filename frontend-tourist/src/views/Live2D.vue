<template>
  <div class="live2d-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <h2>数字人导览</h2>
          <el-tag type="success">本地数字人模型</el-tag>
        </div>
      </template>

      <Live2DCanvas character-name="Mao" character-group="free" />
    </el-card>
  </div>
</template>

<script setup>
import Live2DCanvas from '../components/Live2DCanvas.vue'
</script>

<style scoped>
.live2d-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

</style>


