import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'element-plus': ['element-plus'],
          'element-icons': ['@element-plus/icons-vue'],
          'axios': ['axios']
        }
      }
    },
    chunkSizeWarningLimit: 600
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@framework': path.resolve(__dirname, './src/lib/live2d/Framework/src'),
    }
  },
  server: {
    port: 5173,
    host: true, // 允许局域网访问，手机扫码同 WiFi 可打开
    allowedHosts: true, // 允许通过隧道域名（如 xxx.trycloudflare.com）访问
    proxy: {
      '/api': {
        target: 'http://localhost:18000',
        changeOrigin: true
      },
      '/uploads': {
        target: 'http://localhost:18000',
        changeOrigin: true
      }
    }
  }
})

