import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BillingModal } from './BillingModal'

const getUsageLogsMock = vi.fn()
const getUsageChildrenMock = vi.fn()
const getUsageSummaryMock = vi.fn()
let providerBalanceSyncEnabled = false

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: string | Record<string, unknown>) => {
      const translations: Record<string, string> = {
        'billing.labels.agent_call': '智能设计师',
        'billing.labels.general_call': '通用调用',
        'billing.labels.document_generate': '文档生成',
        'billing.labels.ppt_generate': 'PPT生成',
        'billing.labels.spreadsheet_generate': '表格生成',
        'billing.labels.smart_designer': '智能设计师',
        'billing.labels.web_generate': '网页生成',
        'billing.labels.multimodal_call': '多模态调用',
        'billing.labels.reference_decision': '参考图决策',
        'billing.labels.image_analysis': '图片分析',
        'billing.labels.image_generate': '图片生成',
        'billing.labels.video_generate': '视频生成',
        'billing.labels.mark_recognition': '标记识别',
        'billing.labels.load_skill_rules': '加载 skills 规则',
        'billing.labels.ask_user': '询问用户',
        'billing.labels.spatial_angle': '视角转换',
        'billing.labels.text_recognition': '文字识别',
        'billing.labels.text_redraw': '文字重绘',
        'billing.labels.image_erase': '图片消除',
        'billing.labels.hd_upscale': '图片高清',
        'billing.col_cost': '金额',
        'billing.view_child_costs': '查看子账单',
        'billing.view_child_usage': '查看明细',
        'billing.child_usage_detail_title': '子用量明细',
        'billing.child_usage_model_stats_title': '模型调用统计',
        'billing.child_usage_model_stats_total': '共 {{count}} 次',
        'billing.token_summary': '输入 {{input}} / 输出 {{output}}',
        'billing.summary.multimodal_calls': '多模态模型调用',
        'billing.summary.image_analysis_calls': '图片分析模型调用',
        'billing.summary.image_generation_calls': '图片生成模型调用',
        'billing.summary.video_generation_calls': '视频生成模型调用',
        'billing.summary.mode_label': '模式',
        'billing.summary.total_elapsed': '总耗时',
        'billing.summary.used_models': '使用模型',
        'billing.summary.calls_unit': '次',
        'billing.summary.success_calls': '成功',
        'billing.summary.failed_calls': '失败',
        'billing.request_id': '请求ID',
        'billing.copy_request_id': '复制请求ID',
      }
      const template = translations[key]
      if (!template) {
        if (typeof options === 'string') return options
        if (options && typeof options === 'object' && typeof options.defaultValue === 'string') return options.defaultValue
        return key
      }
      if (options && typeof options === 'object') {
        return template
          .replace('{{input}}', String(options.input ?? ''))
          .replace('{{output}}', String(options.output ?? ''))
          .replace('{{count}}', String(options.count ?? ''))
      }
      return template
    },
  }),
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (state: unknown) => unknown) =>
    selector({
      user: { id: 1, role: 'user', username: 'tester', nickname: 'Tester', balance_cents: 9999 },
      deployType: 'saas',
      providerBalanceSyncEnabled,
    }),
}))

vi.mock('@/api/endpoints/billing', () => ({
  billingApi: {
    getUsageLogs: (...args: unknown[]) => getUsageLogsMock(...args),
    getUsageLogChildren: (...args: unknown[]) => getUsageChildrenMock(...args),
    getUsageLogSummary: (...args: unknown[]) => getUsageSummaryMock(...args),
  },
}))

vi.mock('@/api/endpoints/users', () => ({
  usersApi: {
    getUsers: vi.fn(),
  },
}))

vi.mock('./ResultPreviewDialog', () => ({
  ResultPreviewDialog: () => null,
}))

if (!HTMLElement.prototype.hasPointerCapture) {
  HTMLElement.prototype.hasPointerCapture = () => false
}

if (!HTMLElement.prototype.setPointerCapture) {
  HTMLElement.prototype.setPointerCapture = () => undefined
}

if (!HTMLElement.prototype.releasePointerCapture) {
  HTMLElement.prototype.releasePointerCapture = () => undefined
}

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => undefined
}

describe('BillingModal agent child billing', () => {
  beforeEach(() => {
    getUsageLogsMock.mockReset()
    getUsageChildrenMock.mockReset()
    getUsageSummaryMock.mockReset()
    providerBalanceSyncEnabled = false
    getUsageLogsMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 101,
            parent_id: null,
            user_id: 1,
            task_id: null,
            model_name: 'agent',
            model_label: 'Agent',
            task_type: 'agent',
            amount_cents: 5,
            amount_cents_original: 5,
            billing_label: 'billing.labels.smart_designer',
            elapsed_ms: 2400,
            status: 'success',
            created_at: '2026-03-25T08:00:00Z',
            updated_at: '2026-03-25T08:00:02Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      },
    })
    getUsageChildrenMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 102,
            parent_id: 101,
            user_id: 1,
            task_id: null,
            model_name: 'claude-opus-4-7',
            model_label: 'Opus 4.7',
            task_type: 'multimodal',
            amount_cents: 5,
            amount_cents_original: 5,
            billing_label: 'billing.labels.multimodal_call',
            elapsed_ms: 1300,
            status: 'success',
            params: { input_tokens: 1000, output_tokens: 2000 },
            created_at: '2026-03-25T08:00:00Z',
            updated_at: '2026-03-25T08:00:01Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      },
    })
    getUsageSummaryMock.mockResolvedValue({
      data: {
        id: 101,
        engine: null,
        conversation_id: null,
        agent_run_id: null,
        billing_summary: null,
      },
    })
  })

  it('renders only parent usage rows in the main table', async () => {
    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('智能设计师')).toBeInTheDocument()
    })

    expect(screen.getByRole('columnheader', { name: '金额' })).toBeInTheDocument()
    expect(screen.queryByText('Opus 4.7')).not.toBeInTheDocument()
    expect(getUsageLogsMock).toHaveBeenCalled()
  })

  it('renders aliased model names in the usage table when the API returns raw model ids', async () => {
    getUsageLogsMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 201,
            parent_id: null,
            user_id: 1,
            task_id: 5,
            model_name: 'doubao-seedream-4-5-251128',
            model_label: 'doubao-seedream-4-5-251128',
            task_type: 'text2image',
            amount_cents: 0,
            amount_cents_original: 0,
            billing_label: 'billing.labels.image_generate',
            elapsed_ms: null,
            status: 'pending',
            created_at: '2026-05-21T07:53:35Z',
            updated_at: '2026-05-21T07:53:35Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      },
    })

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Seedream 4.5')).toBeInTheDocument()
    })
    expect(screen.queryByText('doubao-seedream-4-5-251128')).not.toBeInTheDocument()
  })

  it('hides local billing controls and amount surfaces in Provider Balance Sync Mode', async () => {
    const user = userEvent.setup()
    providerBalanceSyncEnabled = true

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('智能设计师')).toBeInTheDocument()
    })

    expect(screen.queryByRole('button', { name: '账单' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '兑换' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '金额' })).not.toBeInTheDocument()
    expect(screen.queryByText('¥0.05')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看子账单' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '查看明细' }))

    await waitFor(() => {
      expect(getUsageChildrenMock).toHaveBeenCalledWith(101)
    })
    expect(screen.getByText('子用量明细')).toBeInTheDocument()
    expect(screen.getAllByText('Opus 4.7').length).toBeGreaterThan(0)
    expect(screen.queryByText('¥0.05')).not.toBeInTheDocument()
  })

  it('renders blocked usage status with the localized label', async () => {
    getUsageLogsMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 301,
            parent_id: null,
            user_id: 1,
            task_id: null,
            model_name: 'agent_harness',
            model_label: 'agent_harness',
            task_type: 'agent',
            amount_cents: 182,
            amount_cents_original: 182,
            billing_label: 'billing.labels.ppt_generate',
            elapsed_ms: 79000,
            status: 'blocked',
            created_at: '2026-04-23T09:05:40Z',
            updated_at: '2026-04-23T09:07:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      },
    })

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('已阻塞')).toBeInTheDocument()
    })

    expect(screen.queryByText('BLOCKED')).not.toBeInTheDocument()
  })

  it('renders completed usage rows as localized success badges and keeps result actions available', async () => {
    getUsageLogsMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 302,
            parent_id: null,
            user_id: 1,
            task_id: 9001,
            model_name: 'agent_harness',
            model_label: 'agent_harness',
            task_type: 'multimodal',
            amount_cents: 30,
            amount_cents_original: 30,
            billing_label: 'billing.labels.general_call',
            elapsed_ms: 38500,
            status: 'COMPLETED',
            created_at: '2026-04-24T03:30:50Z',
            updated_at: '2026-04-24T03:31:29Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      },
    })

    render(<BillingModal open onCancel={() => {}} />)

    const successBadge = await screen.findByText('成功')
    expect(successBadge).toBeInTheDocument()
    expect(successBadge.className).toContain('bg-green-100')
    expect(screen.queryByText('COMPLETED')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看' })).toBeInTheDocument()
  })

  it('loads and shows child billing details for an agent usage row', async () => {
    const user = userEvent.setup()
    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('智能设计师')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '查看子账单' }))

    await waitFor(() => {
      expect(getUsageSummaryMock).toHaveBeenCalledWith(101)
      expect(getUsageChildrenMock).toHaveBeenCalledWith(101)
    })

    expect(screen.getAllByText('Opus 4.7').length).toBeGreaterThan(0)
    expect(screen.getByText('多模态调用')).toBeInTheDocument()
    expect(screen.getByText('输入 1000 / 输出 2000')).toBeInTheDocument()
  })

  it('summarizes child usage calls by model with success and failure counts', async () => {
    const user = userEvent.setup()
    getUsageChildrenMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 401,
            parent_id: 101,
            user_id: 1,
            task_id: null,
            model_name: 'claude-opus-4-7',
            model_label: 'Opus 4.7',
            task_type: 'multimodal',
            amount_cents: 5,
            amount_cents_original: 5,
            billing_label: 'billing.labels.multimodal_call',
            elapsed_ms: 1300,
            status: 'success',
            params: { input_tokens: 1000, output_tokens: 2000 },
            created_at: '2026-03-25T08:00:00Z',
            updated_at: '2026-03-25T08:00:01Z',
          },
          {
            id: 402,
            parent_id: 101,
            user_id: 1,
            task_id: null,
            model_name: 'claude-opus-4-7',
            model_label: 'Opus 4.7',
            task_type: 'multimodal',
            amount_cents: 0,
            amount_cents_original: 5,
            billing_label: 'billing.labels.multimodal_call',
            elapsed_ms: 800,
            status: 'failed',
            params: { input_tokens: 300, output_tokens: 0 },
            created_at: '2026-03-25T08:00:02Z',
            updated_at: '2026-03-25T08:00:03Z',
          },
          {
            id: 403,
            parent_id: 101,
            user_id: 1,
            task_id: null,
            model_name: 'gemini-3.1-pro-preview',
            model_label: 'Gemini 3.1 Pro',
            task_type: 'multimodal',
            amount_cents: 0,
            amount_cents_original: 5,
            billing_label: 'billing.labels.multimodal_call',
            elapsed_ms: 500,
            status: 'blocked',
            params: { input_tokens: 200, output_tokens: 0 },
            created_at: '2026-03-25T08:00:04Z',
            updated_at: '2026-03-25T08:00:05Z',
          },
        ],
        total: 3,
        page: 1,
        page_size: 50,
      },
    })

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('智能设计师')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '查看子账单' }))

    const stats = await screen.findByTestId('child-usage-model-stats')
    expect(within(stats).getByText('模型调用统计')).toBeInTheDocument()
    expect(within(stats).getByText('共 3 次')).toBeInTheDocument()
    expect(within(stats).getByText('Opus 4.7')).toBeInTheDocument()
    expect(within(stats).getByText('Gemini 3.1 Pro')).toBeInTheDocument()
    expect(within(stats).getByText('2 次')).toBeInTheDocument()
    expect(within(stats).getAllByText('成功 1')).toHaveLength(1)
    expect(within(stats).getAllByText('失败 1')).toHaveLength(2)
    expect(within(stats).getByText('成功 0')).toBeInTheDocument()
  })

  it('prefers real child usage rows over harness aggregate details', async () => {
    const user = userEvent.setup()
    getUsageLogsMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 201,
            parent_id: null,
            user_id: 1,
            task_id: null,
            model_name: 'agent_harness',
            model_label: 'Agent Harness',
            task_type: 'agent',
            amount_cents: 6,
            amount_cents_original: 6,
            billing_label: 'billing.labels.ppt_generate',
            elapsed_ms: 1700,
            status: 'success',
            created_at: '2026-03-25T08:00:00Z',
            updated_at: '2026-03-25T08:00:02Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      },
    })
    getUsageSummaryMock.mockResolvedValueOnce({
      data: {
        id: 201,
        engine: 'agent_harness',
        conversation_id: 'conv_201',
        agent_run_id: 'run_201',
        billing_summary: {
          mode: 'ppt',
          mode_label: 'PPT生成',
          multimodal_calls: 2,
          image_analysis_calls: 3,
          image_generation_calls: 1,
          video_generation_calls: 0,
          multimodal_models: ['gpt-4.1'],
          image_analysis_models: ['gemini-3.1-pro-preview'],
          image_models: ['flux-kontext-pro'],
          video_models: [],
          multimodal_model_stats: [
            {
              model_name: 'kimi-k2.5',
              model_label: 'Kimi K2.5',
              calls: 2,
              success_calls: 1,
              failed_calls: 1,
            },
          ],
          image_analysis_model_stats: [
            {
              model_name: 'gemini-3.1-pro-preview',
              model_label: 'Gemini 3.1 Pro Preview',
              calls: 3,
              success_calls: 3,
              failed_calls: 0,
            },
          ],
          image_model_stats: [
            {
              model_name: 'gemini-3.1-flash-image-preview-official',
              model_label: 'NanoBanana2',
              calls: 1,
              success_calls: 1,
              failed_calls: 0,
            },
          ],
          video_model_stats: [],
          total_elapsed_ms: 1700,
        },
      },
    })
    getUsageChildrenMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 202,
            parent_id: 201,
            user_id: 1,
            task_id: null,
            model_name: 'kimi-k2.5',
            model_label: 'Kimi K2.5',
            task_type: 'multimodal',
            amount_cents: 4,
            amount_cents_original: 4,
            billing_label: 'billing.labels.multimodal_call',
            elapsed_ms: 900,
            status: 'success',
            params: {
              kind: 'agent_llm',
              input_tokens: 120,
              output_tokens: 40,
              oneapi_request_id: 'oneapi-child-202',
              request_id: 'req-child-202',
            },
            created_at: '2026-03-25T08:00:00Z',
            updated_at: '2026-03-25T08:00:01Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      },
    })

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('PPT生成')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '查看子账单' }))

    await waitFor(() => {
      expect(getUsageSummaryMock).toHaveBeenCalledWith(201)
      expect(getUsageChildrenMock).toHaveBeenCalledWith(201)
      expect(screen.getAllByText('Kimi K2.5').length).toBeGreaterThan(0)
    })

    expect(screen.queryByTestId('harness-billing-summary')).not.toBeInTheDocument()
    expect(screen.getByText('多模态调用')).toBeInTheDocument()
    expect(screen.getByText('输入 120 / 输出 40')).toBeInTheDocument()
    expect(screen.getByText('oneapi-child-202')).toBeInTheDocument()
  })

  it('renders child usage details inside a dedicated scroll area', async () => {
    const user = userEvent.setup()
    getUsageChildrenMock.mockResolvedValueOnce({
      data: {
        items: Array.from({ length: 20 }, (_, index) => ({
          id: 300 + index,
          parent_id: 101,
          user_id: 1,
          task_id: null,
          model_name: 'claude-opus-4-7',
          model_label: 'Opus 4.7',
          task_type: 'multimodal',
          amount_cents: 5,
          amount_cents_original: 5,
          billing_label: 'billing.labels.multimodal_call',
          elapsed_ms: 1300,
          status: 'success',
          params: { input_tokens: 1000 + index, output_tokens: 2000 + index },
          created_at: '2026-03-25T08:00:00Z',
          updated_at: '2026-03-25T08:00:01Z',
        })),
        total: 20,
        page: 1,
        page_size: 50,
      },
    })

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('智能设计师')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '查看子账单' }))

    await waitFor(() => {
      expect(getUsageSummaryMock).toHaveBeenCalledWith(101)
      expect(getUsageChildrenMock).toHaveBeenCalledWith(101)
    })

    const scrollArea = screen.getByTestId('child-usage-scroll-area')
    expect(scrollArea.className).toContain('flex-1')
    expect(scrollArea.className).toContain('min-h-0')
    expect(scrollArea.className).toContain('overflow-y-auto')
    expect(scrollArea.className).toContain('overscroll-contain')
  })

  it('renders subagent summaries first and expands to show nested tool billing details', async () => {
    const user = userEvent.setup()
    getUsageChildrenMock.mockImplementation(async (usageLogId: number) => {
      if (usageLogId === 101) {
        return {
          data: {
            items: [
              {
                id: 202,
                parent_id: 101,
                user_id: 1,
                task_id: null,
                model_name: 'subagent',
                model_label: 'Subagent',
                task_type: 'agent',
                amount_cents: 9,
                amount_cents_original: 9,
                billing_label: 'billing.labels.agent_call',
                elapsed_ms: 1800,
                status: 'success',
                kind: 'subagent',
                subagent_task_id: 'subagent-202',
                subagent_label: '特色饮品概念图',
                params: {
                  agent_run_id: 'sub-run-202',
                  kind: 'subagent',
                  subagent_task_id: 'subagent-202',
                  subagent_label: '特色饮品概念图',
                },
                created_at: '2026-03-25T08:00:00Z',
                updated_at: '2026-03-25T08:00:02Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 50,
          },
        }
      }

      if (usageLogId === 202) {
        return {
          data: {
            items: [
              {
                id: 203,
                parent_id: 202,
                user_id: 1,
                task_id: null,
                model_name: 'claude-opus-4-7',
                model_label: 'Opus 4.7',
                task_type: 'multimodal',
                amount_cents: 4,
                amount_cents_original: 4,
                billing_label: 'billing.labels.multimodal_call',
                elapsed_ms: 900,
                status: 'success',
                kind: 'agent_llm',
                subagent_task_id: 'subagent-202',
                subagent_label: '特色饮品概念图',
                params: {
                  kind: 'agent_llm',
                  detail: {
                    input_tokens: 111,
                    output_tokens: 222,
                  },
                  subagent_task_id: 'subagent-202',
                  subagent_label: '特色饮品概念图',
                },
                created_at: '2026-03-25T08:00:00Z',
                updated_at: '2026-03-25T08:00:01Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 50,
          },
        }
      }

      throw new Error(`unexpected usageLogId: ${usageLogId}`)
    })

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(getUsageLogsMock).toHaveBeenCalled()
    })

    await user.click(screen.getByRole('button', { name: '查看子账单' }))

    await waitFor(() => {
      expect(getUsageSummaryMock).toHaveBeenCalledWith(101)
      expect(getUsageChildrenMock).toHaveBeenCalledWith(101)
    })

    expect(screen.getByText('特色饮品概念图')).toBeInTheDocument()
    expect(screen.queryByText('Opus 4.7')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '展开下游机器人 特色饮品概念图' }))

    await waitFor(() => {
      expect(getUsageChildrenMock).toHaveBeenCalledWith(202)
    })

    expect(screen.getByText('Opus 4.7')).toBeInTheDocument()
    expect(screen.getByText('输入 111 / 输出 222')).toBeInTheDocument()
  })

  it('renders legacy Chinese billing labels without i18n keys', async () => {
    getUsageLogsMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 201,
            parent_id: null,
            user_id: 1,
            task_id: null,
            model_name: 'agent',
            model_label: 'Agent',
            task_type: 'agent',
            amount_cents: 3,
            amount_cents_original: 3,
            billing_label: 'Agent 调用',
            elapsed_ms: 1200,
            status: 'success',
            params: null,
            created_at: '2026-03-25T09:00:00Z',
            updated_at: '2026-03-25T09:00:01Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      },
    })

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Agent 调用')).toBeInTheDocument()
    })
  })

  it('filters harness usage rows by billing label when selecting smart designer', async () => {
    const user = userEvent.setup()

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(getUsageLogsMock).toHaveBeenCalledWith({ page: 1, page_size: 10 })
    })

    await user.click(screen.getAllByRole('combobox')[0])
    await user.click(screen.getByRole('option', { name: '智能设计师' }))

    await waitFor(() => {
      expect(getUsageLogsMock).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        billing_label: 'billing.labels.smart_designer',
      })
    })
  })

  it('renders a readable fallback label for prompt extraction billing', async () => {
    getUsageLogsMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 301,
            parent_id: null,
            user_id: 1,
            task_id: null,
            model_name: 'gemini-3.1-pro-preview',
            model_label: 'Gemini 3.1 Pro',
            task_type: 'prompt_extraction',
            amount_cents: 2,
            amount_cents_original: 2,
            billing_label: 'billing.labels.prompt_extraction',
            elapsed_ms: 800,
            status: 'success',
            params: null,
            created_at: '2026-04-22T09:00:00Z',
            updated_at: '2026-04-22T09:00:01Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      },
    })

    render(<BillingModal open onCancel={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('提示词提取')).toBeInTheDocument()
    })
  })
})


