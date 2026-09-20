import { createRouter, createWebHistory } from 'vue-router'
import LoginView from './views/LoginView.vue'
import ChatView from './views/ChatView.vue'
import { useAuth } from './composables/useAuth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/login', component: LoginView },
    { path: '/chat', component: ChatView },
  ],
})

router.beforeEach((to) => {
  const { isAuthenticated } = useAuth()
  if (to.path === '/chat' && !isAuthenticated()) return '/login'
  return true
})

export default router
