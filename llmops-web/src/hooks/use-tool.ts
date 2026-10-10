import { onBeforeUnmount, reactive, ref } from 'vue'
import { getApiTool, getApiToolProvidersWithPage } from '@/services/api-tool'
import { type ApiToolProviderView } from '@/models/api-tool'
import { toApiToolProviderView } from '@/utils/api-tool-schema'

export const useGetApiTool = () => {
  // 1.定义hooks所需数据
  const loading = ref(false)
  const api_tool = reactive<Record<string, any>>({})

  // 2.定义加载函数
  const loadApiTool = async (provider_id: string, tool_name: string) => {
    try {
      loading.value = true
      const resp = await getApiTool(provider_id, tool_name)
      const data = resp.data

      Object.assign(api_tool, data)
    } finally {
      loading.value = false
    }
  }

  return { loading, api_tool, loadApiTool }
}

export const useGetApiToolProvidersWithPage = () => {
  // 1.定义hooks所需数据
  const loading = ref(false)
  const api_tool_providers = reactive<ApiToolProviderView[]>([])
  const error = ref('')
  let generation = 0
  onBeforeUnmount(() => {
    generation += 1
  })
  const defaultPaginator = {
    current_page: 1,
    page_size: 20,
    total_page: 0,
    total_record: 0,
  }
  const paginator = reactive({ ...defaultPaginator })

  // 2.定义加载数据函数
  const loadApiToolProviders = async (init: boolean = false, searchWord: string = '') => {
    // 2.1 判断是否是初始化，如果是的话则先初始化分页器
    if (init) {
      generation += 1
      Object.assign(paginator, { ...defaultPaginator })
      api_tool_providers.splice(0)
    } else if (loading.value || paginator.current_page > paginator.total_page) {
      return
    }
    const currentGeneration = generation
    error.value = ''

    // 2.2 加载更多数据并更新数据状态
    try {
      // 2.3 调用接口获取响应数据
      loading.value = true
      const resp = await getApiToolProvidersWithPage(
        paginator.current_page,
        paginator.page_size,
        searchWord,
      )
      if (currentGeneration !== generation) return
      const data = resp.data

      // 2.4 更新分页器
      Object.assign(paginator, data.paginator)

      // 2.5 判断是否存在更多数据
      paginator.current_page += 1

      // 2.6 追加或者是覆盖数据
      if (init) {
        api_tool_providers.splice(
          0,
          api_tool_providers.length,
          ...data.list.map(toApiToolProviderView),
        )
      } else {
        api_tool_providers.push(...data.list.map(toApiToolProviderView))
      }
    } catch (cause) {
      // request 已显示接口错误；加载失败保留分页位置，允许重试。
      if (currentGeneration === generation)
        error.value = cause instanceof Error ? cause.message : '工具加载失败'
    } finally {
      if (currentGeneration === generation) loading.value = false
    }
  }
  return { loading, error, api_tool_providers, paginator, loadApiToolProviders }
}
