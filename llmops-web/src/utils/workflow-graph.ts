import type { Edge, Node } from '@vue-flow/core'
import { NODE_DATA_MAP } from './workflow-defaults'
export function fromGraph(graph: { nodes: Record<string, any>[]; edges: Record<string, any>[] }) {
  return {
    nodes: graph.nodes.map(({ id, node_type, position, ...data }) => ({
      id,
      type: node_type,
      position: position || { x: 100, y: 100 },
      data: {
        ...structuredClone(NODE_DATA_MAP[node_type] || {}),
        ...data,
        ...(node_type === 'llm'
          ? { model_config: data.model_config || data.language_model_config }
          : {}),
      },
    })) as Node[],
    edges: graph.edges.map((e) => ({ ...e, animated: false, type: 'smoothstep' })) as Edge[],
  }
}
export function toGraph(nodes: Node[], edges: Edge[]) {
  return {
    nodes: nodes.map(({ id, type, position, data }) => {
      const copy = JSON.parse(JSON.stringify(data))
      // Backend returns language_model_config; its input alias is model_config.
      if (type === 'llm') {
        copy.model_config = copy.model_config || copy.language_model_config
        delete copy.language_model_config
      }
      delete copy.id
      delete copy.node_type
      return { ...copy, id, node_type: type, position: { x: position.x, y: position.y } }
    }),
    edges: edges.map(({ id, source, target }) => ({
      id,
      source,
      target,
      source_type: nodes.find((n) => n.id === source)?.type,
      target_type: nodes.find((n) => n.id === target)?.type,
    })),
  }
}
