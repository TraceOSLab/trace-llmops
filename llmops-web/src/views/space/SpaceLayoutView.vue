<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
const route = useRoute(),
  router = useRouter(),
  createType = ref(''),
  searchWord = ref(String(route.query.search_word || ''))
const definitions: Record<string, { title: string; type: string; description: string }> = {
  apps: { title: '应用', type: 'app', description: '将模型与业务连接，让每个想法都能运行。' },
  workflows: {
    title: '工作流',
    type: 'workflow',
    description: '可视化编排任务，追踪从输入到输出的每一步。',
  },
  datasets: {
    title: '知识库',
    type: 'dataset',
    description: '整理你的业务知识，为 AI 提供可靠的上下文。',
  },
  tools: { title: '工具', type: 'tool', description: '连接外部服务，扩展应用的行动能力。' },
}
const current = computed(() => definitions[route.path.split('/')[2]] || definitions.apps)
function search(value: string) {
  router.replace({ path: route.path, query: { search_word: value } })
}
let alive = true
onBeforeUnmount(() => {
  alive = false
})
watch(
  () => route.query.create,
  async (value) => {
    if (value === '1') {
      await nextTick()
      if (alive) createType.value = current.value.type
    }
  },
  { immediate: true },
)
watch(
  () => route.query.search_word,
  (value) => (searchWord.value = String(value || '')),
)
</script>
<template>
  <div class="resource-page">
    <div class="resource-heading">
      <div>
        <p class="eyebrow">BUILD / {{ current.type.toUpperCase() }}</p>
        <h1>{{ current.title }}</h1>
        <p class="page-description">{{ current.description }}</p>
      </div>
      <a-button type="primary" @click="createType = current.type"
        ><template #icon><icon-plus /></template>创建{{ current.title }}</a-button
      >
    </div>
    <div class="resource-toolbar">
      <span>我的{{ current.title }}</span
      ><a-input-search
        v-model="searchWord"
        allow-clear
        :placeholder="`搜索${current.title}`"
        @search="search"
        @clear="search('')"
      />
    </div>
    <router-view :create-type="createType" @update-create-type="createType = $event" />
  </div>
</template>
