import { createTranslationFixture } from '@/store/testing/translationFixture'
import type { ComponentProps } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { HomeHarnessInteractionForm } from './HomeHarnessInteractionForm'

vi.mock('./HomeDesignSystemPreviewDialog', () => ({
  HomeDesignSystemPreviewDialog: ({
    open,
    designSystem,
  }: {
    open: boolean
    designSystem: { id: string; title: string } | null
  }) => (open && designSystem ? (
    <div data-testid="mock-design-system-preview">
      {designSystem.id}:{designSystem.title}
    </div>
  ) : null),
}))

const t = createTranslationFixture({})
type HomeHarnessInteractionFormProps = ComponentProps<typeof HomeHarnessInteractionForm>

describe('HomeHarnessInteractionForm', () => {
  it('submits multiple ask_user choice questions with per-question other input', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const buildProps = (): HomeHarnessInteractionFormProps => ({
      requestId: 'functions.ask_user:9',
      kind: 'ask_user',
      language: 'en',
      isDark: false,
      t: t,
      schema: {
        title: 'Need a few choices',
        submit_label: 'Submit',
        questions: [
          {
            id: 'design_system',
            header: 'Design',
            question: 'Choose a design system',
            type: 'single',
            options: [
              { label: 'Atelier Zero', value: 'atelier_zero' },
              { label: 'Framer', value: 'framer' },
            ],
          },
          {
            id: 'tone',
            header: 'Tone',
            question: 'Choose a tone',
            type: 'single',
            options: [
              { label: 'Calm', value: 'calm' },
              { label: 'Sharp', value: 'sharp' },
            ],
          },
        ],
      },
      onSubmit,
    })

    const { rerender } = render(<HomeHarnessInteractionForm {...buildProps()} />)

    await user.click(screen.getByRole('button', { name: 'Atelier Zero' }))
    await user.click(screen.getAllByRole('button', { name: 'Other' })[1])
    await user.type(screen.getByRole('textbox', { name: 'Choose a tone' }), 'Bold and direct')
    rerender(<HomeHarnessInteractionForm {...buildProps()} />)
    expect(screen.getByRole('textbox', { name: 'Choose a tone' })).toHaveValue('Bold and direct')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onSubmit).toHaveBeenCalledWith(
      'functions.ask_user:9',
      JSON.stringify({
        design_system: {
          type: 'option',
          value: 'atelier_zero',
          label: 'Atelier Zero',
        },
        tone: {
          type: 'other',
          value: 'Bold and direct',
          label: 'Other: Bold and direct',
        },
      }),
      'Atelier Zero / Other: Bold and direct',
      undefined,
      {
        design_system: {
          type: 'option',
          value: 'atelier_zero',
          label: 'Atelier Zero',
        },
        tone: {
          type: 'other',
          value: 'Bold and direct',
          label: 'Other: Bold and direct',
        },
      },
    )
  })

  it('adds a fixed other option for multiple ask_user questions and keeps slash-joined display text', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:10"
        kind="ask_user"
        language="en"
        isDark={false}
        t={t}
        schema={{
          title: 'Audience selection',
          submit_label: 'Submit',
          questions: [
            {
              id: 'audience',
              header: 'Audience',
              question: 'Audience',
              type: 'multiple',
              options: [
                { label: 'Tourists', value: 'tourists' },
                { label: 'Locals', value: 'locals' },
              ],
            },
          ],
        }}
        onSubmit={onSubmit}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Tourists' }))
    await user.click(screen.getByRole('button', { name: 'Other' }))
    await user.type(screen.getByRole('textbox', { name: 'Audience' }), 'Students')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onSubmit).toHaveBeenCalledWith(
      'functions.ask_user:10',
      JSON.stringify({
        audience: [
          {
            type: 'option',
            value: 'tourists',
            label: 'Tourists',
          },
          {
            type: 'other',
            value: 'Students',
            label: 'Other: Students',
          },
        ],
      }),
      'Tourists / Other: Students',
      undefined,
      {
        audience: [
          {
            type: 'option',
            value: 'tourists',
            label: 'Tourists',
          },
          {
            type: 'other',
            value: 'Students',
            label: 'Other: Students',
          },
        ],
      },
    )
  })

  it('submits a sparse ask_user input question as structured input', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:input"
        kind="ask_user"
        language="en"
        isDark={false}
        t={t}
        schema={{
          title: 'Brand detail',
          submit_label: 'Submit',
          questions: [
            {
              id: 'brand_name',
              header: 'Brand',
              question: 'What brand name should I use?',
              type: 'input',
              options: [],
            },
          ],
        }}
        onSubmit={onSubmit}
      />,
    )

    await user.type(screen.getByRole('textbox', { name: 'What brand name should I use?' }), 'Acme Studio')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onSubmit).toHaveBeenCalledWith(
      'functions.ask_user:input',
      JSON.stringify({
        brand_name: {
          type: 'input',
          value: 'Acme Studio',
          label: 'Acme Studio',
        },
      }),
      'Acme Studio',
      undefined,
      {
        brand_name: {
          type: 'input',
          value: 'Acme Studio',
          label: 'Acme Studio',
        },
      },
    )
  })

  it('preserves ask_user other input across parent rerenders with the same request', async () => {
    const user = userEvent.setup()
    const buildProps = (): HomeHarnessInteractionFormProps => ({
      requestId: 'functions.ask_user:11',
      kind: 'ask_user',
      language: 'en',
      isDark: false,
      t: t,
      schema: {
        title: 'Tone input',
        submit_label: 'Submit',
        questions: [
          {
            id: 'tone',
            header: 'Tone',
            question: 'Tone',
            type: 'single',
            options: [
              { label: 'Warm', value: 'warm' },
              { label: 'Direct', value: 'direct' },
            ],
          },
        ],
      },
      onSubmit: vi.fn(),
    })

    const { rerender } = render(<HomeHarnessInteractionForm {...buildProps()} />)

    await user.click(screen.getByRole('button', { name: 'Other' }))
    await user.type(screen.getByRole('textbox', { name: 'Tone' }), 'Warm and editorial')
    rerender(<HomeHarnessInteractionForm {...buildProps()} />)

    expect(screen.getByRole('textbox', { name: 'Tone' })).toHaveValue('Warm and editorial')
  })

  it('reflects submitted ask_user answers after the parent marks the form submitted', async () => {
    const user = userEvent.setup()
    const buildProps = (
      overrides: Partial<HomeHarnessInteractionFormProps> = {},
    ): HomeHarnessInteractionFormProps => ({
      requestId: 'functions.ask_user:15',
      kind: 'ask_user',
      language: 'en',
      isDark: false,
      t: t,
      schema: {
        title: 'Brand brief',
        submit_label: 'Submit',
        questions: [
          {
            id: 'industry',
            header: 'Industry',
            question: 'Industry',
            type: 'single',
            options: [
              { label: 'Technology', value: 'technology' },
              { label: 'Education', value: 'education' },
            ],
          },
        ],
      },
      onSubmit: vi.fn(),
      ...overrides,
    })

    const { rerender } = render(<HomeHarnessInteractionForm {...buildProps()} />)

    await user.click(screen.getByRole('button', { name: 'Technology' }))

    rerender(<HomeHarnessInteractionForm {...buildProps({
      answers: {
        industry: {
          type: 'option',
          value: 'technology',
          label: 'Technology',
        },
      },
      status: 'submitted',
      submittedLabel: 'Technology',
    })} />)

    expect(screen.getAllByText('Technology')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'Submit' })).not.toBeInTheDocument()
  })

  it('does not render schema-less ask_user payloads', () => {
    const { container } = render(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:4"
        kind="ask_user"
        language="en"
        isDark={false}
        t={t}
        schema={null}
        question="Which deck should I review?"
        onSubmit={vi.fn()}
      />,
    )

    expect(container.firstChild).toBeNull()
  })

  it('shows an unsupported message for legacy ask_user field schemas', () => {
    render(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:legacy"
        kind="ask_user"
        language="en"
        isDark={false}
        t={t}
        schema={{
          title: 'Legacy prompt',
          fields: [
            {
              id: 'tone',
              label: 'Tone',
              type: 'text',
              required: true,
            },
          ],
        }}
        onSubmit={vi.fn()}
      />,
    )

    expect(screen.getByText('Legacy prompt')).toBeInTheDocument()
    expect(screen.getByText('This question was created by an older interaction format and cannot be continued. Please start a new request.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Submit' })).not.toBeInTheDocument()
  })

  it('sends the finish plan interview feedback only during planning phases', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    const { rerender } = render(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:finish"
        kind="ask_user"
        phase="executing"
        language="en"
        isDark={false}
        t={t}
        schema={{
          title: 'Plan questions',
          submit_label: 'Submit',
          questions: [
            {
              id: 'direction',
              header: 'Direction',
              question: 'Pick a direction',
              type: 'multiple',
              options: [
                { label: 'Editorial', value: 'editorial' },
                { label: 'Product', value: 'product' },
              ],
            },
          ],
        }}
        onSubmit={onSubmit}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Enough info, continue' })).not.toBeInTheDocument()

    rerender(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:finish"
        kind="ask_user"
        phase="planning"
        language="en"
        isDark={false}
        t={t}
        schema={{
          title: 'Plan questions',
          submit_label: 'Submit',
          questions: [
            {
              id: 'direction',
              header: 'Direction',
              question: 'Pick a direction',
              type: 'multiple',
              options: [
                { label: 'Editorial', value: 'editorial' },
                { label: 'Product', value: 'product' },
              ],
            },
          ],
        }}
        onSubmit={onSubmit}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Enough info, continue' }))

    expect(onSubmit).toHaveBeenCalledWith(
      'functions.ask_user:finish',
      expect.stringContaining('Stop asking clarifying questions'),
      'Information is enough. Continue planning.',
      false,
      expect.objectContaining({
        __finish_plan_interview: true,
      }),
    )
  })

  it('renders ask_user markdown briefing content ahead of the form without duplicating the title', () => {
    render(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:12"
        kind="ask_user"
        language="zh"
        isDark={false}
        t={t}
        content={'### Gate A：品牌战略简报\n\n- 两岸人文融合\n- 青岛商务办公'}
        schema={{
          title: 'Gate A：品牌战略简报确认',
          submit_label: '确认并继续',
          questions: [
            {
              id: 'approval',
              header: '确认',
              question: '是否继续',
              type: 'single',
              options: [
                { label: '继续', value: 'continue' },
                { label: '调整', value: 'revise' },
              ],
            },
          ],
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Gate A：品牌战略简报', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('两岸人文融合')).toBeInTheDocument()
    expect(screen.queryByText('Gate A：品牌战略简报确认')).not.toBeInTheDocument()
  })

  it('renders markdown briefing from question when content is absent for schema-based ask_user forms', () => {
    render(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:13"
        kind="ask_user"
        language="zh"
        isDark={false}
        t={t}
        question={'### Gate A：品牌战略简报\n\n- 两岸人文融合\n- 青岛商务办公'}
        schema={{
          title: 'Gate A：品牌战略简报确认',
          submit_label: '确认并继续',
          questions: [
            {
              id: 'approval',
              header: '确认',
              question: '是否继续',
              type: 'single',
              options: [
                { label: '继续', value: 'continue' },
                { label: '调整', value: 'revise' },
              ],
            },
          ],
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Gate A：品牌战略简报', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('两岸人文融合')).toBeInTheDocument()
    expect(screen.queryByText('Gate A：品牌战略简报确认')).not.toBeInTheDocument()
  })

  it('renders markdown briefing from fallback content when content and question are absent', () => {
    render(
      <HomeHarnessInteractionForm
        requestId="functions.ask_user:14"
        kind="ask_user"
        language="zh"
        isDark={false}
        t={t}
        fallbackContent={'### Gate A：品牌战略简报\n\n- 两岸人文融合\n- 青岛商务办公'}
        schema={{
          title: 'Gate A：品牌战略简报确认',
          submit_label: '确认并继续',
          questions: [
            {
              id: 'approval',
              header: '确认',
              question: '是否继续',
              type: 'single',
              options: [
                { label: '继续', value: 'continue' },
                { label: '调整', value: 'revise' },
              ],
            },
          ],
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Gate A：品牌战略简报', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('两岸人文融合')).toBeInTheDocument()
    expect(screen.queryByText('Gate A：品牌战略简报确认')).not.toBeInTheDocument()
  })

  it('aligns quick brief select and action button styles with the usage controls language', () => {
    render(
      <HomeHarnessInteractionForm
        requestId="quick-brief:conv-1"
        kind="quick_brief"
        language="zh"
        isDark={false}
        t={t}
        schema={{
          title: 'Quick brief',
          fields: [
            {
              id: 'industry',
              label: '行业',
              type: 'select',
              placeholder: '选择行业',
              options: [
                { label: 'SaaS', value: 'saas' },
                { label: 'Consumer', value: 'consumer' },
              ],
            },
            {
              id: 'design_system',
              label: '设计体系',
              type: 'cards',
              required: true,
              options: [
                {
                  label: 'Arc Browser',
                  value: 'arc-browser',
                  description: 'Modern browser-inspired product system.',
                  metadata: {
                    category: 'Product & SaaS',
                    palette: ['#F8FAFC', '#E2E8F0', '#111827', '#7C3AED'],
                    references: ['Arc Browser'],
                  },
                },
              ],
            },
          ],
        }}
      />,
    )

    const selectTrigger = screen.getByRole('combobox', { name: '行业' })
    expect(selectTrigger.className).toContain('rounded-xl')
    expect(selectTrigger.className).toContain('bg-[var(--app-control)]')
    expect(selectTrigger.className).toContain('border-[var(--app-border)]')

    const designSystemCard = screen.getByRole('button', {
      name: /Arc Browser Modern browser-inspired product system/,
    })
    expect(designSystemCard.className).toContain('rounded-xl')
    expect(designSystemCard.className).toContain('border-[var(--app-border)]')
    expect(designSystemCard.className).toContain('bg-[var(--app-control)]')

    const submitButton = screen.getByRole('button', { name: '提交' })
    expect(submitButton.className).toContain('rounded-xl')
    expect(submitButton.className).toContain('border-[var(--app-border)]')
    expect(submitButton.className).toContain('bg-[var(--app-control)]')
  })

  it('opens the design system preview from a design system card option', async () => {
    const user = userEvent.setup()

    render(
      <HomeHarnessInteractionForm
        requestId="design-system:conv-1"
        kind="design_system_picker"
        language="zh"
        isDark={false}
        t={t}
        schema={{
          title: '选择设计体系',
          fields: [
            {
              id: 'design_system_id',
              label: '设计体系',
              type: 'cards',
              required: true,
              options: [
                {
                  label: 'Arc Browser',
                  value: 'arc-browser',
                  description: 'Modern browser-inspired product system.',
                  metadata: {
                    category: 'Product & SaaS',
                    palette: ['#F8FAFC', '#E2E8F0', '#111827', '#7C3AED'],
                    references: ['Arc Browser'],
                  },
                },
              ],
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: '示例' }))

    expect(screen.getByTestId('mock-design-system-preview')).toHaveTextContent('arc-browser:Arc Browser')
  })

  it('renders refs metadata and preview action on the same row for design system cards', () => {
    render(
      <HomeHarnessInteractionForm
        requestId="design-system:conv-compact"
        kind="design_system_picker"
        language="zh"
        isDark={false}
        t={t}
        schema={{
          title: '选择设计体系',
          fields: [
            {
              id: 'design_system_id',
              label: '设计体系',
              type: 'cards',
              required: true,
              options: [
                {
                  label: 'kami（紙 / 纸）',
                  value: 'kami',
                  description: 'Editorial & Print',
                  metadata: {
                    mood: 'Editorial & Print',
                    palette: ['#F7F5EC', '#1F3D6D', '#FFFFFF', '#D7E3F0'],
                    references: ['kami（紙 / 纸）'],
                  },
                },
              ],
            },
          ],
        }}
      />,
    )

    const refsText = screen.getByText('Refs: kami（紙 / 纸）')
    const previewButton = screen.getByRole('button', { name: '示例' })
    const metaRow = refsText.closest('[data-testid="design-system-card-meta-row"]')

    expect(metaRow).not.toBeNull()
    expect(metaRow).toContainElement(refsText)
    expect(metaRow).toContainElement(previewButton)
  })

  it('shows a check icon for selected radio and checkbox quick brief options', async () => {
    const user = userEvent.setup()

    const { container } = render(
      <HomeHarnessInteractionForm
        requestId="quick-brief:conv-2"
        kind="quick_brief"
        language="zh"
        isDark={false}
        t={t}
        schema={{
          title: 'Quick brief',
          fields: [
            {
              id: 'content_focus',
              label: '内容侧重点',
              type: 'radio',
              required: true,
              options: [
                { label: '趋势分析', value: 'trend_analysis' },
                { label: '案例展示', value: 'case_showcase' },
              ],
            },
            {
              id: 'speaker_notes',
              label: '是否需要演讲备注',
              type: 'checkbox',
              required: true,
              options: [
                { label: '每页添加演讲备注', value: 'add_notes' },
                { label: '不需要备注', value: 'no_notes' },
              ],
            },
          ],
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: '趋势分析' }))
    await user.click(screen.getByRole('button', { name: '每页添加演讲备注' }))

    expect(
      screen.getByRole('button', { name: '趋势分析' }).querySelector('svg.lucide-check'),
    ).not.toBeNull()
    expect(
      screen.getByRole('button', { name: '每页添加演讲备注' }).querySelector('svg.lucide-check'),
    ).not.toBeNull()
    expect(container.querySelectorAll('svg.lucide-check')).toHaveLength(2)
  })

  it('lets quick brief radio and checkbox fields submit custom other answers with human-readable labels', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(
      <HomeHarnessInteractionForm
        requestId="quick-brief:conv-3"
        kind="quick_brief"
        language="zh"
        isDark={false}
        t={t}
        schema={{
          title: 'Quick brief',
          submit_label: '继续',
          fields: [
            {
              id: 'content_focus',
              label: '内容侧重点',
              type: 'radio',
              required: true,
              options: [
                { label: '趋势分析', value: 'trend_analysis' },
                { label: '案例展示', value: 'case_showcase' },
              ],
            },
            {
              id: 'speaker_notes',
              label: '演讲备注',
              type: 'checkbox',
              required: true,
              options: [
                { label: '每页添加演讲备注', value: 'add_notes' },
              ],
            },
          ],
        }}
        onSubmit={onSubmit}
      />,
    )

    const otherButtons = screen.getAllByRole('button', { name: 'Other' })
    expect(otherButtons).toHaveLength(2)

    await user.click(otherButtons[0])
    await user.type(screen.getByRole('textbox', { name: '内容侧重点' }), '专家访谈')
    await user.click(screen.getByRole('button', { name: '每页添加演讲备注' }))
    await user.click(otherButtons[1])
    await user.type(screen.getByRole('textbox', { name: '演讲备注' }), '附带过渡台词')
    await user.click(screen.getByRole('button', { name: '继续' }))

    expect(onSubmit).toHaveBeenCalledWith(
      'quick-brief:conv-3',
      JSON.stringify({
        content_focus: {
          type: 'other',
          value: '专家访谈',
          label: 'Other: 专家访谈',
        },
        speaker_notes: [
          'add_notes',
          {
            type: 'other',
            value: '附带过渡台词',
            label: 'Other: 附带过渡台词',
          },
        ],
      }),
      'Other: 专家访谈 / 每页添加演讲备注 / Other: 附带过渡台词',
      undefined,
      {
        content_focus: {
          type: 'other',
          value: '专家访谈',
          label: 'Other: 专家访谈',
        },
        speaker_notes: [
          'add_notes',
          {
            type: 'other',
            value: '附带过渡台词',
            label: 'Other: 附带过渡台词',
          },
        ],
      },
    )
  })
})
