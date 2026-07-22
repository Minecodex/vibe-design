import { getModelDisplayName } from '@/utils/modelDisplayName'

const TOOL_LABELS: Record<string, string> = {
  generate_image: '生成图片 / Generate Image',
  generate_video: '生成视频 / Generate Video',
  analyze_image: '图片分析 / Analyze Image',
  write_files: '写入文件 / Write Files',
  bash: '执行命令 / Bash',
  ask_user: '询问用户 / Ask User',
  web_search: '联网搜索 / Web Search',
  search_web: '联网搜索 / Web Search',
  Agent: '子代理 / Agent',
}

export function getHomeToolDisplayName(toolName: string | null | undefined) {
  const normalized = String(toolName || '').replace(/^lc_/, '')
  return TOOL_LABELS[normalized] || `${normalized} / ${normalized}`
}

export function getHomeModelDisplayName(
  modelLabel: string | null | undefined,
  modelName: string | null | undefined,
) {
  return getModelDisplayName(modelLabel, modelName)
}
