<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getAppsWithPage } from '@/services/app'
import { getWorkflowsWithPage } from '@/services/workflow'
const apps = ref<any[]>([]),
  workflows = ref<any[]>([]),
  loading = ref(true),
  error = ref('')
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [a, w] = await Promise.all([
      getAppsWithPage({ current_page: 1, page_size: 6, search_word: '' }),
      getWorkflowsWithPage({ current_page: 1, page_size: 6 }),
    ])
    apps.value = a.data.list
    workflows.value = w.data.list
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(load)
const shortcuts = [
  {
    path: '/space/apps?create=1',
    title: '创建 AI 应用',
    text: '让模型、知识与工具协同工作',
    icon: 'icon-command',
    tag: 'AGENT',
  },
  {
    path: '/space/workflows?create=1',
    title: '编排工作流',
    text: '把复杂任务变成清晰的执行步骤',
    icon: 'icon-branch',
    tag: 'WORKFLOW',
  },
  {
    path: '/space/datasets?create=1',
    title: '建立知识库',
    text: '让你的应用理解专属业务知识',
    icon: 'icon-storage',
    tag: 'KNOWLEDGE',
  },
]
</script>
<template>
  <div class="page dashboard">
    <div class="page-heading">
      <div>
        <p class="eyebrow">YOUR AI WORKSPACE</p>
        <h1>从想法，到可用的 AI 应用。</h1>
        <p class="page-description">在 Trace 中连接模型、知识与工具，构建属于你的智能工作方式。</p>
      </div>
      <router-link to="/assistant" class="text-link"
        >与 AI 助手一起开始 <icon-arrow-right
      /></router-link>
    </div>
    <div class="quick-grid">
      <router-link v-for="item in shortcuts" :key="item.path" :to="item.path" class="quick-card"
        ><div class="quick-top">
          <span class="feature-icon"><component :is="item.icon" :size="24" /></span
          ><span class="eyebrow">{{ item.tag }}</span>
        </div>
        <h2>{{ item.title }} <icon-arrow-right /></h2>
        <p>{{ item.text }}</p></router-link
      >
    </div>
    <div v-if="error" class="error-panel" role="alert">
      {{ error }} <a-button @click="load">重新加载</a-button>
    </div>
    <div class="dashboard-columns">
      <section class="panel">
        <div class="section-heading">
          <h2>最近更新的应用</h2>
          <router-link to="/space/apps">查看全部 <icon-arrow-right /></router-link>
        </div>
        <a-skeleton v-if="loading" :animation="true"><a-skeleton-line :rows="4" /></a-skeleton
        ><template v-else
          ><router-link
            v-for="app in apps"
            :key="app.id"
            :to="`/space/apps/${app.id}`"
            class="resource-row"
            ><a-avatar shape="square" :image-url="app.icon">{{ app.name[0] }}</a-avatar>
            <div>
              <strong>{{ app.name }}</strong>
              <p>{{ app.description || '开始配置你的应用' }}</p>
            </div>
            <span class="status-badge" :class="{ published: app.status === 'published' }">{{
              app.status === 'published' ? '已发布' : '草稿'
            }}</span></router-link
          >
          <div v-if="!apps.length" class="empty-state">
            <icon-command :size="30" />
            <h3>你的第一个应用，从这里开始</h3>
            <p>连接一个模型，写下它要完成的任务。</p>
            <router-link to="/space/apps?create=1" class="text-link">创建应用 →</router-link>
          </div></template
        >
      </section>
      <section class="panel">
        <div class="section-heading">
          <h2>最近更新的工作流</h2>
          <router-link to="/space/workflows">查看全部 <icon-arrow-right /></router-link>
        </div>
        <a-skeleton v-if="loading" :animation="true"><a-skeleton-line :rows="4" /></a-skeleton
        ><template v-else
          ><router-link
            v-for="w in workflows"
            :key="w.id"
            :to="`/space/workflows/${w.id}`"
            class="resource-row"
            ><span class="feature-icon"><icon-branch /></span>
            <div>
              <strong>{{ w.name }}</strong>
              <p>{{ w.node_count }} 个节点 · {{ w.description || '可视化任务编排' }}</p>
            </div>
            <icon-arrow-right
          /></router-link>
          <div v-if="!workflows.length" class="empty-state">
            <icon-branch :size="30" />
            <h3>将步骤连接起来</h3>
            <p>从输入到输出，清晰掌握每一步。</p>
            <router-link to="/space/workflows?create=1" class="text-link">创建工作流 →</router-link>
          </div></template
        >
      </section>
    </div>
    <div class="explore-strip">
      <span class="feature-icon"><icon-book :size="24" /></span>
      <div>
        <h3>不必从空白开始</h3>
        <p>探索应用模板与内置工具，为你的下一个想法找到起点。</p>
      </div>
      <router-link to="/store/apps" class="text-link"
        >浏览资源中心 <icon-arrow-right
      /></router-link>
    </div>
    <footer class="page-footer">Trace LLMOPS <span>Crafted by Youyou</span></footer>
  </div>
</template>
