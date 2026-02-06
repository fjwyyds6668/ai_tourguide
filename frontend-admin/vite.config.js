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
    },
  },
  server: {
    port: 5522,
    proxy: {
      '/api': {
        target: 'http://localhost:18000',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://localhost:18000',
        changeOrigin: true,
      },
    },
  },
})
