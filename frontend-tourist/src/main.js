import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
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

const loadingEl = document.getElementById('app-loading')
if (loadingEl) {
  loadingEl.classList.add('app-loaded')
  requestAnimationFrame(() => {
    setTimeout(() => loadingEl.remove(), 220)
  })
}

