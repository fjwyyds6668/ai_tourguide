import { createRouter, createWebHistory } from 'vue-router'

// 路由懒加载：首屏只加载 Home，其它页面进入时再加载，减小首包体积
const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import(/* webpackChunkName: "home" */ '../views/Home.vue')
  },
  {
    path: '/attractions',
    name: 'Attractions',
    component: () => import(/* webpackChunkName: "attractions" */ '../views/Attractions.vue')
  },
  {
    path: '/voice-guide',
    name: 'VoiceGuide',
    component: () => import(/* webpackChunkName: "voice-guide" */ '../views/VoiceGuide.vue')
  },
  {
    path: '/history',
    name: 'History',
    component: () => import(/* webpackChunkName: "history" */ '../views/History.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router

