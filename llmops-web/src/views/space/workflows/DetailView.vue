<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { VueFlow, useVueFlow, Panel, type Node, type Edge, type Connection } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { MiniMap } from '@vue-flow/minimap'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/minimap/dist/style.css'
import '@vue-flow/controls/dist/style.css'
import dagre from 'dagre'
import { Message } from '@arco-design/web-vue'
import {
  getWorkflow,
  getDraftGraph,
  publishWorkflow,
  cancelPublishWorkflow,
} from '@/services/workflow'
import { post } from '@/utils/request'
import { NODE_DATA_MAP } from '@/utils/workflow-defaults'
import { fromGraph, toGraph } from '@/utils/workflow-graph'
import StartNode from './components/nodes/StartNode.vue'
import LLMNode from './components/nodes/LLMNode.vue'
import ToolNode from './components/nodes/ToolNode.vue'
import CodeNode from './components/nodes/CodeNode.vue'
import DatasetRetrievalNode from './components/nodes/DatasetRetrievalNode.vue'
import TemplateTransformNode from './components/nodes/TemplateTransformNode.vue'
import HttpRequestNode from './components/nodes/HttpRequestNode.vue'
import EndNode from './components/nodes/EndNode.vue'
import StartInfo from './components/infos/StartNodeInfo.vue'
import LLMInfo from './components/infos/LLMNodeInfo.vue'
import ToolInfo from './components/infos/ToolNodeInfo.vue'
import CodeInfo from './components/infos/CodeNodeInfo.vue'
import DatasetInfo from './components/infos/DatasetRetrievalNodeInfo.vue'
import TemplateInfo from './components/infos/TemplateTransformNodeInfo.vue'
import HttpInfo from './components/infos/HttpRequestNodeInfo.vue'
import EndInfo from './components/infos/EndNodeInfo.vue'
import DebugModal from './components/DebugModal.vue'
const route = useRoute(),
  id = String(route.params.workflow_id)
const nodeTypes = {
  start: markRaw(StartNode),
  llm: markRaw(LLMNode),
  tool: markRaw(ToolNode),
  code: markRaw(CodeNode),
  dataset_retrieval: markRaw(DatasetRetrievalNode),
  template_transform: markRaw(TemplateTransformNode),
  http_request: markRaw(HttpRequestNode),
  end: markRaw(EndNode),
}
const infoTypes: Record<string, any> = {
  start: markRaw(StartInfo),
  llm: markRaw(LLMInfo),
  tool: markRaw(ToolInfo),
  code: markRaw(CodeInfo),
  dataset_retrieval: markRaw(DatasetInfo),
  template_transform: markRaw(TemplateInfo),
  http_request: markRaw(HttpInfo),
  end: markRaw(EndInfo),
}
const nodes = ref<any[]>([]),
  edges = ref<any[]>([]),
  workflow = ref<any>({}),
  selected = ref<any>(),
  panel = ref(false),
  debug = ref(false),
  saving = ref(false),
  error = ref(''),
  loaded = ref(false),
  saved = ref(''),
  localFormDirty = ref(false)
const { fitView, onNodeClick } = useVueFlow()
const snapshot = computed(() => JSON.stringify(toGraph(nodes.value, edges.value)))
const dirty = computed(
  () => loaded.value && (snapshot.value !== saved.value || localFormDirty.value),
)
let saveTail: Promise<void> = Promise.resolve()
function confirmDiscard() {
  return !localFormDirty.value || window.confirm('节点表单尚未应用，放弃这些输入吗？')
}
onNodeClick(({ node }) => {
  if (selected.value?.id === node.id) return
  if (!confirmDiscard()) return
  selected.value = node
  localFormDirty.value = false
  panel.value = true
  debug.value = false
})
async function load() {
  error.value = ''
  try {
    const [w, g] = await Promise.all([getWorkflow(id), getDraftGraph(id)])
    workflow.value = w.data
    const graph = fromGraph(g.data)
    nodes.value = graph.nodes
    edges.value = graph.edges
    await nextTick()
    saved.value = snapshot.value
    loaded.value = true
    await nextTick()
    fitView({ padding: 0.3, maxZoom: 1 })
  } catch (e: any) {
    error.value = e.message
  }
}
function closePanel(visible: boolean) {
  if (!visible && !confirmDiscard()) return
  panel.value = visible
  if (!visible) localFormDirty.value = false
}
function add(type: string) {
  if (!confirmDiscard()) return
  if ((type === 'start' || type === 'end') && nodes.value.some((n) => n.type === type)) {
    Message.warning('只能有一个开始节点和结束节点')
    return
  }
  const node: Node = {
    id: crypto.randomUUID(),
    type,
    position: {
      x: 150 + (nodes.value.length % 3) * 360,
      y: 120 + Math.floor(nodes.value.length / 3) * 260,
    },
    data: structuredClone(NODE_DATA_MAP[type]),
  }
  node.data.title += `_${nodes.value.length + 1}`
  nodes.value.push(node)
  selected.value = node
  localFormDirty.value = false
  panel.value = true
  debug.value = false
}
function connect(c: Connection) {
  if (
    c.source === c.target ||
    edges.value.some((e) => e.source === c.source && e.target === c.target)
  )
    return
  edges.value.push({ ...c, id: crypto.randomUUID(), type: 'smoothstep' })
}
function update(data: any) {
  const node = nodes.value.find((n) => n.id === data.id)
  if (!node) return
  node.data = { ...node.data, ...data }
  selected.value = node
  localFormDirty.value = false
  Message.success('节点配置已应用，请保存草稿')
}
function save() {
  if (localFormDirty.value) {
    Message.warning('请先应用右侧节点表单，再保存或运行')
    return Promise.reject(new Error('节点表单尚未应用'))
  }
  const value = snapshot.value
  if (value === saved.value) return saveTail
  saving.value = true
  error.value = ''
  const run = saveTail
    .catch(() => {})
    .then(async () => {
      await post(`/workflows/${id}/draft-graph`, { body: JSON.parse(value) })
      saved.value = value
      workflow.value.is_debug_passed = false
    })
    .catch((e) => {
      error.value = e.message
      throw e
    })
    .finally(() => (saving.value = false))
  saveTail = run
  return run
}
async function run() {
  await save()
  panel.value = false
  debug.value = true
}
async function publish() {
  await save()
  await publishWorkflow(id)
  workflow.value = (await getWorkflow(id)).data
  Message.success('工作流已发布')
}
async function unpublish() {
  await cancelPublishWorkflow(id)
  workflow.value = (await getWorkflow(id)).data
}
function layout() {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', ranksep: 180, nodesep: 100 })
  g.setDefaultEdgeLabel(() => ({}))
  nodes.value.forEach((n) => g.setNode(n.id, { width: 280, height: 160 }))
  edges.value.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  nodes.value = nodes.value.map((n) => ({
    ...n,
    position: { x: g.node(n.id).x, y: g.node(n.id).y },
  }))
  nextTick(() => fitView({ padding: 0.2, maxZoom: 1 }))
}
function remove() {
  if (!selected.value) return
  const nodeId = selected.value.id
  nodes.value = nodes.value.filter((n) => n.id !== nodeId)
  edges.value = edges.value.filter((e) => e.source !== nodeId && e.target !== nodeId)
  selected.value = undefined
  panel.value = false
  localFormDirty.value = false
}
const beforeUnload = (e: BeforeUnloadEvent) => {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onMounted(() => {
  load()
  window.addEventListener('beforeunload', beforeUnload)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
onBeforeRouteLeave(() => !dirty.value || window.confirm('草稿尚未保存，确定离开吗？'))
watch(snapshot, () => {
  if (loaded.value && snapshot.value !== saved.value) workflow.value.is_debug_passed = false
})
</script>
<template>
  <div class="flow-editor">
    <header class="editor-header">
      <div class="editor-title">
        <router-link to="/space/workflows" class="icon-button" aria-label="返回工作流列表"
          ><icon-arrow-left /></router-link
        ><span class="feature-icon"><icon-branch /></span>
        <div>
          <h2>{{ workflow.name || '工作流' }}</h2>
          <p class="save-status">
            {{
              saving ? '正在保存…' : error ? '保存失败' : dirty ? '有未保存的更改' : '草稿已保存'
            }}
            · {{ workflow.status === 'published' ? '已发布' : '未发布' }}
          </p>
        </div>
      </div>
      <div class="editor-actions">
        <a-button :loading="saving" @click="save">保存草稿</a-button
        ><a-button @click="run"><icon-play-arrow /> 调试</a-button
        ><a-popconfirm
          v-if="workflow.status === 'published'"
          content="取消发布后关联应用将无法调用此工作流。"
          @ok="unpublish"
          ><a-button>取消发布</a-button></a-popconfirm
        ><a-button type="primary" :disabled="!workflow.is_debug_passed || dirty" @click="publish"
          >发布工作流</a-button
        >
      </div>
    </header>
    <div v-if="error" class="flow-error" role="alert">
      {{ error }}<a-button v-if="!loaded" @click="load">重试</a-button>
    </div>
    <div class="workflow-mobile-hint">
      请在桌面浏览器中编排工作流。<br />手机上可返回列表管理工作流。
    </div>
    <div class="flow-body workflow-canvas">
      <aside class="node-library">
        <p class="eyebrow">添加节点</p>
        <button v-for="(item, type) in NODE_DATA_MAP" :key="type" @click="add(String(type))">
          <span class="node-symbol">{{
            String(type) === 'start' ? '↗' : String(type) === 'end' ? '↘' : '◇'
          }}</span
          ><span
            ><strong>{{ item.title }}</strong
            ><small>{{ item.description }}</small></span
          ><icon-plus />
        </button>
        <p class="library-help">
          拖动节点连接点建立数据流。<br />选中节点或连线后按 Delete 删除。<br />配置完成后保存并调试。
        </p>
      </aside>
      <div class="flow-stage">
        <vue-flow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          :min-zoom="0.2"
          :max-zoom="2"
          :delete-key-code="['Backspace', 'Delete']"
          :fit-view-params="{ maxZoom: 1, padding: 0.2 }"
          fit-view-on-init
          @connect="connect"
          ><background :gap="20" pattern-color="#d7e1db" /><mini-map
            pannable
            zoomable /><controls /><panel position="top-left"
            ><a-button size="small" @click="layout">自动布局</a-button
            ><a-button size="small" @click="fitView({ padding: 0.2, maxZoom: 1 })"
              >适应画布</a-button
            ></panel
          >
          <div v-if="panel && selected" class="node-form">
            <component
              :is="infoTypes[selected.type!]"
              :key="selected.id"
              :node="selected"
              :loading="saving"
              :visible="true"
              @update-node="update"
              @dirty="localFormDirty = $event"
              @update:visible="closePanel"
            />
            <div class="node-form-actions">
              <a-button
                size="small"
                @click="
                  () => {
                    if (confirmDiscard()) {
                      panel = false
                      localFormDirty = false
                    }
                  }
                "
                >关闭配置</a-button
              ><a-popconfirm content="删除节点及其连线？" @ok="remove"
                ><a-button size="small" status="danger">删除节点</a-button></a-popconfirm
              >
            </div>
          </div>
          <debug-modal
            :workflow_id="id"
            v-model:visible="debug"
            @complete="async () => (workflow = (await getWorkflow(id)).data)"
        /></vue-flow>
      </div>
    </div>
  </div>
</template>
<style scoped>
.flow-editor {
  height: 100dvh;
  display: flex;
  flex-direction: column;
}
.flow-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.node-library {
  width: 224px;
  background: #fff;
  border-right: 1px solid #e1e8e3;
  padding: 24px 12px;
  overflow: auto;
  flex-shrink: 0;
}
.node-library > .eyebrow {
  padding: 0 12px;
}
.node-library > button {
  display: flex;
  text-align: left;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 14px 10px;
  border-radius: 8px;
  margin: 2px 0;
}
.node-library > button:hover {
  background: #eef6f1;
}
.node-library strong {
  font-size: 12px;
  display: block;
  color: #435a4c;
}
.node-library small {
  font-size: 10px;
  display: block;
  color: #98a19a;
  white-space: nowrap;
  width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 4px;
}
.node-symbol {
  color: #0f766e;
  font-size: 19px;
}
.node-library > button > svg {
  font-size: 12px;
  color: #97aba0;
}
.library-help {
  font-size: 10px;
  line-height: 1.9;
  color: #9aa79f;
  border-top: 1px solid #edf1ee;
  padding: 18px 10px;
  margin-top: 20px;
}
.flow-stage {
  flex: 1;
  min-width: 0;
  position: relative;
  background: #f7faf8;
}
.node-form-actions {
  position: absolute;
  right: 0;
  top: 0;
  z-index: 60;
  display: flex;
  gap: 8px;
  padding: 8px;
  background: white;
  border-bottom: 1px solid #eee;
  width: 400px;
  justify-content: flex-end;
}
.node-form :deep([id$='node-info']) {
  padding-top: 56px;
}
.flow-error {
  background: #fff0ed;
  color: #943f32;
  padding: 12px 24px;
  font-size: 12px;
}
.save-status {
  margin-top: 6px;
}
@media (max-width: 767px) {
  .flow-body {
    display: none;
  }
  .editor-actions {
    display: none;
  }
}
</style>
