export const NODE_DATA_MAP: Record<string, any> = {
  start: {
    title: '开始节点',
    description: '工作流的起点节点，支持定义工作流的起点输入等信息',
    inputs: [],
  },
  llm: {
    title: '大语言模型',
    description: '调用大语言模型，根据输入参数和提示词生成回复。',
    prompt: '',
    model_config: {
      provider: '',
      model: '',
      parameters: {
        frequency_penalty: 0.2,
        max_tokens: 8192,
        presence_penalty: 0.2,
        temperature: 0.5,
        top_p: 0.85,
      },
    },
    inputs: [],
    outputs: [{ name: 'output', type: 'string', value: { type: 'generated', content: '' } }],
  },
  tool: {
    title: '扩展插件',
    description: '调用插件广场或自定义API插件，支持能力扩展和复用',
    tool_type: '',
    provider_id: '',
    tool_id: '',
    params: {},
    inputs: [],
    outputs: [{ name: 'text', type: 'string', value: { type: 'generated', content: '' } }],
    meta: {
      type: 'api_tool',
      provider: { id: '', name: '', label: '', icon: '', description: '' },
      tool: { id: '', name: '', label: '', description: '', params: {} },
    },
  },
  dataset_retrieval: {
    title: '知识库检索',
    description: '根据输入的参数，在选定的知识库中检索相关片段并召回，返回切片列表',
    dataset_ids: [],
    retrieval_config: {
      retrieval_strategy: 'semantic',
      k: 4,
      score: 0,
    },
    inputs: [
      {
        name: 'query',
        type: 'string',
        value: { type: 'ref', content: { ref_node_id: '', ref_var_name: '' } },
      },
    ],
    outputs: [
      { name: 'combine_documents', type: 'string', value: { type: 'generated', content: '' } },
    ],
    meta: { datasets: [] },
  },
  template_transform: {
    title: '模板转换',
    description: '对多个字符串变量的格式进行处理',
    template: '',
    inputs: [],
    outputs: [{ name: 'output', type: 'string', value: { type: 'generated', content: '' } }],
  },
  http_request: {
    title: 'HTTP请求',
    description: '配置外部API服务，并发起请求。',
    url: '',
    method: 'get',
    inputs: [],
    outputs: [
      { name: 'status_code', type: 'int', value: { type: 'generated', content: 0 } },
      { name: 'text', type: 'string', value: { type: 'generated', content: '' } },
    ],
  },
  code: {
    title: 'Python代码执行',
    description: '编写代码，处理输入输出变量来生成返回值',
    code: '',
    inputs: [],
    outputs: [],
  },
  end: {
    title: '结束节点',
    description: '工作流的结束节点，支持定义工作流最终输出的变量等信息',
    outputs: [],
  },
}
