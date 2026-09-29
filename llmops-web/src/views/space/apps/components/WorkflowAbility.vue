<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getWorkflowsWithPage } from '@/services/workflow'
import { updateDraftAppConfig } from '@/services/app'
const props = defineProps<{ appId: string; modelValue: any[] }>(),
  emit = defineEmits(['update:modelValue']),
  workflows = ref<any[]>([])
onMounted(async () => {
  let page = 1,
    total = 1
  while (page <= total) {
    const res = await getWorkflowsWithPage({
      current_page: page,
      page_size: 100,
      status: 'published',
    })
    workflows.value.push(...res.data.list)
    total = res.data.paginator.total_page
    page++
  }
})
async function change(ids: any) {
  await updateDraftAppConfig(props.appId, { workflows: ids })
  emit(
    'update:modelValue',
    workflows.value.filter((w) => ids.includes(w.id)),
  )
}
</script>
<template>
  <div class="mb-4">
    <label class="block mb-2 text-gray-600">可调用的工作流</label
    ><a-select
      multiple
      :model-value="(modelValue || []).map((w) => (typeof w === 'string' ? w : w.id))"
      placeholder="选择已发布的工作流"
      @change="change"
      ><a-option v-for="w in workflows" :key="w.id" :value="w.id">{{ w.name }}</a-option></a-select
    >
  </div>
</template>
