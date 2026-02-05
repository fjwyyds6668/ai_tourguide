import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { public: true } },
  { path: '/register', name: 'Register', component: () => import('../views/Register.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../layouts/AdminLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
      { path: 'characters', name: 'Characters', component: () => import('../views/CharactersManagement.vue') },
      { path: 'knowledge', name: 'Knowledge', component: () => import('../views/KnowledgeBase.vue') },
      { path: 'analytics', name: 'Analytics', component: () => import('../views/Analytics.vue') },
      { path: 'settings', name: 'Settings', component: () => import('../views/Settings.vue') },
      { path: 'attractions', redirect: '/knowledge' },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  const user = localStorage.getItem('user')
  const isAuth = !!(token && user)
  if (to.meta.public) {
    next()
    return
  }
  if (to.meta.requiresAuth && !isAuth) {
    next('/login')
    return
  }
  next()
})

export default router
