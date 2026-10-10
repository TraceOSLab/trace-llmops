<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { get, post } from '@/utils/request'
import { apiPrefix } from '@/config'
import { Message } from '@arco-design/web-vue'
const route = useRoute(),
  config = ref<any>(),
  error = ref(''),
  loading = ref(false)
const link = computed(() =>
  config.value?.web_app?.token ? `${location.origin}/web-apps/${config.value.web_app.token}` : '',
)
async function load() {
  error.value = ''
  try {
    config.value = (await get<any>(`/apps/${route.params.app_id}/published-config`)).data
  } catch (e: any) {
    error.value = e.message
  }
}
async function regenerate() {
  loading.value = true
  try {
    await post(`/apps/${route.params.app_id}/published-config/regenerate-web-app-token`)
    await load()
    Message.success('访问链接已更新')
  } finally {
    loading.value = false
  }
}
async function copy() {
  try {
    await navigator.clipboard.writeText(link.value)
    Message.success('已复制链接')
  } catch {
    Message.error('复制失败，请手动选择链接复制')
  }
}
onMounted(load)
</script>
<template>
  <div class="page publish-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">DEPLOY / SHARE</p>
        <h1>让应用开始工作</h1>
        <p class="page-description">分享独立聊天页面，或通过 API 集成到你的产品。</p>
      </div>
    </div>
    <div v-if="error" class="error-panel">{{ error }}<a-button @click="load">重试</a-button></div>
    <div v-else-if="config" class="publish-grid">
      <section class="panel">
        <span class="feature-icon"><icon-link :size="24" /></span>
        <h2 class="mt-5 mb-3">WebApp 聊天页面</h2>
        <p class="page-description">
          访问者需要登录 Youyou 账号。对话使用已发布配置，草稿修改需重新发布后生效。
        </p>
        <template v-if="config.web_app.status === 'published'"
          ><label class="block mt-6 mb-2 text-gray-500 text-xs">访问链接</label
          ><a-input :model-value="link" readonly aria-label="访问链接" />
          <div class="flex gap-3 mt-4">
            <a-button type="primary" @click="copy">复制链接</a-button
            ><a :href="link" target="_blank" rel="noopener"
              ><a-button>打开应用 <icon-launch /></a-button
            ></a>
          </div>
          <div class="mt-8 border-t pt-4">
            <a-popconfirm content="重置后原分享链接立即失效，确定继续？" @ok="regenerate"
              ><a-button :loading="loading" status="warning" type="text"
                >重置访问链接</a-button
              ></a-popconfirm
            >
          </div></template
        ><a-alert v-else class="mt-6">应用尚未发布，点击顶部“发布应用”生成访问链接。</a-alert>
      </section>
      <section class="panel">
        <span class="feature-icon"><icon-code :size="24" /></span>
        <h2 class="mt-5 mb-3">通过 API 调用</h2>
        <p class="page-description">使用 API 密钥将当前应用接入你自己的服务。</p>
        <pre class="api-example">
POST {{ apiPrefix }}/openapi/chat
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{{ JSON.stringify({ app_id: route.params.app_id, query: '你好', stream: true }, null, 2) }}</pre>
        <router-link to="/openapi" class="text-link">查看接入文档 <icon-arrow-right /></router-link>
      </section>
    </div>
    <a-spin v-else />
  </div>
</template>
<style scoped>
.publish-page {
  max-width: 1200px;
}
.publish-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}
.api-example {
  background: #f7f9f8;
  border: 1px solid #e4ebe6;
  border-radius: 8px;
  padding: 20px;
  font-size: 12px;
  line-height: 1.8;
  margin: 24px 0;
  color: #567165;
}
@media (max-width: 767px) {
  .publish-grid {
    grid-template-columns: 1fr;
  }
}
</style>
