import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Attractions from '../views/Attractions.vue'
import VoiceGuide from '../views/VoiceGuide.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/attractions',
    name: 'Attractions',
    component: Attractions
  },
  {
    path: '/voice-guide',
    name: 'VoiceGuide',
    component: VoiceGuide
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router

