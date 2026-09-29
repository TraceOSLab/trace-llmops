<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getCurrentUser } from '@/services/account'
import { logout } from '@/services/auth'
import { useAccountStore } from '@/stores/account'
import { useCredentialStore } from '@/stores/credential'
import SettingModal from './components/SettingModal.vue'
const route = useRoute(),
  router = useRouter(),
  account = useAccountStore()
const collapsed = ref(false),
  mobileOpen = ref(false),
  settings = ref(false)
const links = [
  { path: '/home', label: '工作台', icon: 'icon-apps', section: '工作空间' },
  { path: '/assistant', label: 'AI 助手', icon: 'icon-message' },
  { path: '/space/apps', label: '应用', icon: 'icon-command' },
  { path: '/space/workflows', label: '工作流', icon: 'icon-branch' },
  { path: '/space/datasets', label: '知识库', icon: 'icon-storage' },
  { path: '/space/tools', label: '工具', icon: 'icon-tool' },
  { path: '/store/apps', label: '应用模板', icon: 'icon-book', section: '资源中心' },
  { path: '/store/tools', label: '内置工具', icon: 'icon-apps' },
  { path: '/openapi', label: '开放 API', icon: 'icon-code', section: '开发者' },
]
onMounted(async () => {
  try {
    account.update((await getCurrentUser()).data)
  } catch {
    /* request layer shows error */
  }
})
async function exit() {
  try {
    await logout()
  } finally {
    useCredentialStore().clear()
    account.clear()
    await router.replace('/auth/login')
  }
}
</script>
<template>
  <div class="trace-shell" :class="{ collapsed, 'mobile-open': mobileOpen }">
    <button
      v-if="mobileOpen"
      class="sidebar-mask"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    />
    <aside class="trace-sidebar">
      <router-link to="/home" class="brand"
        ><img src="/favicon.svg" alt="Trace" /><span>Trace <small>LLMOPS</small></span></router-link
      >
      <nav aria-label="主导航">
        <template v-for="link in links" :key="link.path">
          <p v-if="link.section" class="nav-section">{{ link.section }}</p>
          <router-link
            :to="link.path"
            class="nav-link"
            :class="{ active: route.path.startsWith(link.path) }"
            :title="link.label"
            @click="mobileOpen = false"
            ><component :is="link.icon" :size="19" /><span>{{ link.label }}</span></router-link
          >
        </template>
      </nav>
      <div class="sidebar-bottom">
        <div class="creator"><span class="status-dot" /> Built by Youyou</div>
        <button class="account-button" @click="settings = true">
          <a-avatar :size="32" :image-url="account.account.avatar">{{
            account.account.name?.[0] || 'Y'
          }}</a-avatar
          ><span
            ><strong>{{ account.account.name || '我的账号' }}</strong
            ><small>账号设置</small></span
          ><icon-settings /></button
        ><button class="signout" @click="exit">退出登录</button>
      </div>
    </aside>
    <div class="trace-workspace">
      <header class="workspace-bar">
        <button
          class="desktop-toggle icon-button"
          aria-label="折叠导航"
          @click="collapsed = !collapsed"
        >
          <icon-menu-fold /></button
        ><button class="mobile-toggle icon-button" aria-label="打开导航" @click="mobileOpen = true">
          <icon-menu /></button
        ><span
          >工作空间 <span class="slash">/</span>
          <strong>{{
            links.find((l) => route.path.startsWith(l.path))?.label || '资源详情'
          }}</strong></span
        ><span class="workspace-label">TRACE / PERSONAL</span>
      </header>
      <main class="workspace-main"><router-view :key="route.path" /></main>
    </div>
    <setting-modal v-model:visible="settings" />
  </div>
</template>
