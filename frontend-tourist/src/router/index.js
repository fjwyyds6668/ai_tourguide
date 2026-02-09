import { createRouter, createWebHistory } from 'vue-router'

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

