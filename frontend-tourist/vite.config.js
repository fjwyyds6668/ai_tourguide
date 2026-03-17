import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import Components from 'unplugin-vue-components/vite'
import AutoImport from 'unplugin-auto-import/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import compression from 'vite-plugin-compression'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({ resolvers: [ElementPlusResolver()] }),
    Components({ resolvers: [ElementPlusResolver()] }),
    compression({ algorithm: 'gzip', ext: '.gz' }),
  ],
  build: {
    target: 'esnext',
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
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

