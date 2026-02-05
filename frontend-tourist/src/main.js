import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// 按需注册图标，减少首包体积（仅注册项目实际使用的图标）
import {
  Microphone,
  Location,
  Document,
  Fold,
  Expand,
  Search,
  Picture,
  ChatDotRound,
  VideoPause
} from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

const app = createApp(App)
const pinia = createPinia()

const icons = {
  Microphone,
  Location,
  Document,
  Fold,
  Expand,
  Search,
  Picture,
  ChatDotRound,
  VideoPause
}
for (const [key, component] of Object.entries(icons)) {
  app.component(key, component)
}

app.use(pinia)
app.use(router)
app.use(ElementPlus)

app.mount('#app')

