<script setup lang="ts">
import { onErrorCaptured, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
const error = ref(''),
  route = useRoute(),
  revision = ref(0)
onErrorCaptured((e) => {
  error.value = e.message
  return false
})
watch(
  () => route.fullPath,
  () => (error.value = ''),
)
function retry() {
  error.value = ''
  revision.value++
}
</script>
<template>
  <div v-if="error" class="global-error" role="alert">
    <span>操作未完成：{{ error }}</span
    ><a-button size="small" @click="retry">重新加载页面</a-button
    ><a-button size="small" type="text" @click="error = ''">关闭</a-button>
  </div>
  <router-view :key="revision" />
</template>
<style scoped>
.global-error {
  position: fixed;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  max-width: 90vw;
  background: #fff4ee;
  border: 1px solid #e2c4ac;
  box-shadow: 0 5px 25px #0001;
  border-radius: 10px;
  padding: 12px 18px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: #844b2f;
  font-size: 12px;
}
</style>
