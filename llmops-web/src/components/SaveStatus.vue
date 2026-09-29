<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { appDraftQueueFor, workflowDraftQueue } from '@/utils/draft-queue'
const props = defineProps<{ workflow?: boolean }>()
const route = useRoute()
const queue = computed(() =>
  props.workflow ? workflowDraftQueue : appDraftQueueFor(String(route.params.app_id)),
)
const dirty = () => !!(queue.value.state.pending || queue.value.state.error)
const beforeUnload = (e: BeforeUnloadEvent) => {
  if (dirty()) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload))
onBeforeRouteLeave(() => !dirty() || window.confirm('更改尚未保存成功，确定离开吗？'))
</script>
<template>
  <span class="save-status" role="status"
    ><template v-if="queue.state.pending">正在保存…</template
    ><template v-else-if="queue.state.error"
      ><span class="text-red-700">保存失败</span>
      <button @click="queue.retry().catch(() => {})">重试</button></template
    ><template v-else>{{ queue.state.savedAt ? '更改已保存' : '已加载草稿' }}</template></span
  >
</template>
