import { it, expect } from 'vitest'
import { fromGraph, toGraph } from '../src/utils/workflow-graph'
it('round trips all eight node types and preserves configuration, positions and edges', () => {
  const types = [
    'start',
    'llm',
    'tool',
    'code',
    'dataset_retrieval',
    'http_request',
    'template_transform',
    'end',
  ]
  const graph = {
    nodes: types.map((node_type, i) => ({
      id: String(i),
      node_type,
      title: node_type,
      position: { x: i * 350, y: 100 },
      inputs: [],
      outputs: [],
      ...(node_type === 'llm'
        ? {
            language_model_config: {
              provider: 'chosen',
              model: 'my/model',
              parameters: { temperature: 0.3 },
            },
          }
        : {}),
    })),
    edges: [{ id: 'e', source: '0', source_type: 'start', target: '1', target_type: 'llm' }],
  }
  const ui = fromGraph(graph)
  ui.nodes[1].data.model_config.model = 'edited/model'
  const output = toGraph(ui.nodes, ui.edges)
  expect(output.nodes).toHaveLength(8)
  expect(output.nodes[1].model_config.model).toBe('edited/model')
  expect(output.nodes[1].language_model_config).toBeUndefined()
  expect(output.nodes[1].position).toEqual({ x: 350, y: 100 })
  expect(output.edges).toEqual(graph.edges)
})

it('restores generated output contracts omitted by backend serialization', () => {
  const graph = fromGraph({
    nodes: [
      {
        id: 'llm',
        node_type: 'llm',
        language_model_config: { provider: 'chosen', model: 'chosen/model' },
      },
    ],
    edges: [],
  })
  expect(graph.nodes[0].data.outputs[0].name).toBe('output')
  expect(graph.nodes[0].data.model_config.model).toBe('chosen/model')
  graph.nodes[0].data.outputs[0].name = 'changed'
  const fresh = fromGraph({ nodes: [{ id: 'llm', node_type: 'llm' }], edges: [] })
  expect(fresh.nodes[0].data.outputs[0].name).toBe('output')
})
