import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PendingInteraction } from '@/api/endpoints/agent'

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string) => fallback ?? _key,
    }),
  }
})

import { InteractionCard } from './InteractionCard'

describe('InteractionCard', () => {
  it('does not render invalid ask_user payloads with no question or options', () => {
    const { container } = render(
      <InteractionCard
        interaction={{
          request_id: '',
          question: '',
          kind: 'ask_user',
          schema: {
            title: '',
            questions: [{
              id: 'choice',
              header: 'Choice',
              question: 'Choice',
              type: 'single',
              options: [],
            }],
          },
        }}
        onRespond={vi.fn()}
      />,
    )

    expect(container.firstChild).toBeNull()
    expect(screen.queryByRole('button', { name: 'canvas.chat.interaction.other' })).not.toBeInTheDocument()
  })

  it('renders markdown tables with visible cell borders in the question', () => {
    render(
      <InteractionCard
        interaction={{
          request_id: 'req-1',
          question: '| Name | Value |\n| --- | --- |\n| Foo | Bar |',
          kind: 'ask_user',
          schema: {
            title: 'Continue',
            questions: [{
              id: 'choice',
              header: 'Choice',
              question: 'Choice',
              type: 'single',
              options: [{ label: 'Continue', value: 'continue' }, { label: 'Revise', value: 'revise' }],
            }],
          },
        }}
        onRespond={vi.fn()}
      />,
    )

    const headerCell = screen.getByRole('columnheader', { name: 'Name' })
    const bodyCell = screen.getByRole('cell', { name: 'Foo' })

    expect(headerCell).toHaveStyle({ borderWidth: '1px', borderStyle: 'solid' })
    expect(bodyCell).toHaveStyle({ borderWidth: '1px', borderStyle: 'solid' })
  })

  it('submits ask_user question answers in the structured choice shape', async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()
    const buildInteraction = (): PendingInteraction => ({
      request_id: 'functions.ask_user:7',
      question: 'Need a few choices',
      kind: 'ask_user',
      schema: {
        title: 'Quick brief',
        submit_label: 'Submit',
        questions: [
          {
            id: 'direction',
            header: 'Direction',
            question: 'Direction',
            type: 'single',
            options: [
              { label: 'Option A', value: 'a' },
              { label: 'Option B', value: 'b' },
            ],
          },
          {
            id: 'tone',
            header: 'Tone',
            question: 'Tone',
            type: 'single',
            options: [
              { label: 'Calm', value: 'calm' },
              { label: 'Sharp', value: 'sharp' },
            ],
          },
        ],
      },
    })

    const { rerender } = render(
      <InteractionCard
        interaction={buildInteraction()}
        onRespond={onRespond}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Option A' }))
    await user.click(screen.getAllByRole('button', { name: 'Other' })[1])
    await user.type(screen.getByRole('textbox', { name: 'Tone' }), 'Warm and editorial')
    rerender(
      <InteractionCard
        interaction={buildInteraction()}
        onRespond={onRespond}
      />,
    )
    expect(screen.getByRole('textbox', { name: 'Tone' })).toHaveValue('Warm and editorial')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onRespond).toHaveBeenCalledWith(
      'functions.ask_user:7',
      JSON.stringify({
        direction: {
          type: 'option',
          value: 'a',
          label: 'Option A',
        },
        tone: {
          type: 'other',
          value: 'Warm and editorial',
          label: 'Other: Warm and editorial',
        },
      }),
      'Option A / Other: Warm and editorial',
      {
        direction: {
          type: 'option',
          value: 'a',
          label: 'Option A',
        },
        tone: {
          type: 'other',
          value: 'Warm and editorial',
          label: 'Other: Warm and editorial',
        },
      },
    )
  })

  it('does not auto-submit a single-question single-select until the confirm button is clicked', async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()

    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:single',
          question: 'Pick a direction',
          kind: 'ask_user',
          schema: {
            title: 'Direction',
            submit_label: 'Confirm',
            questions: [
              {
                id: 'direction',
                header: 'Direction',
                question: 'Direction',
                type: 'single',
                options: [
                  { label: 'Option A', value: 'a' },
                  { label: 'Option B', value: 'b' },
                ],
              },
            ],
          },
        }}
        onRespond={onRespond}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Option A' }))
    expect(onRespond).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(onRespond).toHaveBeenCalledWith(
      'functions.ask_user:single',
      JSON.stringify({
        direction: {
          type: 'option',
          value: 'a',
          label: 'Option A',
        },
      }),
      'Option A',
      {
        direction: {
          type: 'option',
          value: 'a',
          label: 'Option A',
        },
      },
    )
  })

  it('renders ask_user markdown briefing content for schema-based interaction cards', () => {
    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:brief',
          question: 'Gate A：品牌战略简报确认',
          content: '### Gate A：品牌战略简报\n\n- 两岸文化融合\n- 商务办公第三空间',
          kind: 'ask_user',
          schema: {
            title: 'Gate A：品牌战略简报确认',
            submit_label: '确认并继续',
            questions: [
              {
                id: 'approval',
                header: '确认',
                question: '是否继续',
                type: 'single',
                options: [{ label: '继续', value: 'continue' }, { label: '调整', value: 'revise' }],
              },
            ],
          },
        }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Gate A：品牌战略简报', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('两岸文化融合')).toBeInTheDocument()
    expect(screen.queryByText('Gate A：品牌战略简报确认')).not.toBeInTheDocument()
  })

  it('renders ask_user markdown briefing from question when content is absent', () => {
    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:brief-question',
          question: '### Gate A：品牌战略简报\n\n- 两岸文化融合\n- 商务办公第三空间',
          kind: 'ask_user',
          schema: {
            title: 'Gate A：品牌战略简报确认',
            submit_label: '确认并继续',
            questions: [
              {
                id: 'approval',
                header: '确认',
                question: '是否继续',
                type: 'single',
                options: [{ label: '继续', value: 'continue' }, { label: '调整', value: 'revise' }],
              },
            ],
          },
        }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Gate A：品牌战略简报', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('两岸文化融合')).toBeInTheDocument()
    expect(screen.queryByText('Gate A：品牌战略简报确认')).not.toBeInTheDocument()
  })

  it('renders ask_user markdown briefing from fallback content when question and content are absent', () => {
    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:fallback-content',
          kind: 'ask_user',
          schema: {
            title: 'Gate A：品牌战略简报确认',
            submit_label: '确认并继续',
            questions: [
              {
                id: 'approval',
                header: '确认',
                question: '是否继续',
                type: 'single',
                options: [{ label: '继续', value: 'continue' }, { label: '调整', value: 'revise' }],
              },
            ],
          },
        }}
        fallbackContent={'### Gate A：品牌战略简报\n\n- 两岸文化融合\n- 商务办公第三空间'}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Gate A：品牌战略简报', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('两岸文化融合')).toBeInTheDocument()
    expect(screen.queryByText('Gate A：品牌战略简报确认')).not.toBeInTheDocument()
  })

  it('adds a fixed other option for multiple ask_user questions and keeps slash-joined display text', async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()

    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:8',
          question: 'Need multiple audiences',
          kind: 'ask_user',
          schema: {
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
          },
        }}
        onRespond={onRespond}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Tourists' }))
    await user.click(screen.getByRole('button', { name: 'Other' }))
    await user.type(screen.getByRole('textbox', { name: 'Audience' }), 'Students')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onRespond).toHaveBeenCalledWith(
      'functions.ask_user:8',
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

  it('submits ask_user input questions as structured input answers', async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()

    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:input',
          question: 'Need brand detail',
          kind: 'ask_user',
          schema: {
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
          },
        }}
        onRespond={onRespond}
      />,
    )

    await user.type(screen.getByRole('textbox', { name: 'What brand name should I use?' }), 'Acme Studio')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onRespond).toHaveBeenCalledWith(
      'functions.ask_user:input',
      JSON.stringify({
        brand_name: {
          type: 'input',
          value: 'Acme Studio',
          label: 'Acme Studio',
        },
      }),
      'Acme Studio',
      {
        brand_name: {
          type: 'input',
          value: 'Acme Studio',
          label: 'Acme Studio',
        },
      },
    )
  })

  it('allows optional ask_user input questions to submit empty answers', async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()

    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:optional-input',
          question: 'Optional reference',
          kind: 'ask_user',
          schema: {
            title: 'Optional reference',
            submit_label: 'Submit',
            questions: [
              {
                id: 'reference_url',
                header: 'Reference',
                question: 'Paste a URL if you have one.',
                type: 'input',
                required: false,
                options: [],
              },
            ],
          },
        }}
        onRespond={onRespond}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onRespond).toHaveBeenCalledWith(
      'functions.ask_user:optional-input',
      JSON.stringify({
        reference_url: {
          type: 'input',
          value: '',
          label: '',
        },
      }),
      'Optional reference',
      {
        reference_url: {
          type: 'input',
          value: '',
          label: '',
        },
      },
    )
  })

  it('renders radio and checkbox choices as compact small-radius buttons with consistent sizing', () => {
    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:9',
          question: 'Need layout consistency',
          kind: 'ask_user',
          schema: {
            title: 'Layout check',
            questions: [
              {
                id: 'direction',
                header: 'Direction',
                question: 'Direction',
                type: 'single',
                options: [
                  { label: 'Option A', value: 'a' },
                  { label: 'Option B', value: 'b' },
                ],
              },
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
          },
        }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Option A' })).toHaveStyle({ minHeight: '56px', padding: '12px 16px', fontSize: '13px', borderRadius: '12px' })
    const otherButtons = screen.getAllByRole('button', { name: 'Other' })
    expect(otherButtons[0]).toHaveStyle({ minHeight: '56px', padding: '12px 16px', fontSize: '13px', borderRadius: '12px' })
    expect(otherButtons[1]).toHaveStyle({ minHeight: '42px', padding: '8px 14px', fontSize: '13px', borderRadius: '12px' })
    expect(screen.getByRole('button', { name: 'Tourists' })).toHaveStyle({ minHeight: '42px', padding: '8px 14px', fontSize: '13px', borderRadius: '12px' })
  })

  it('keeps the schema other button content left-aligned beside the edit icon', () => {
    render(
      <InteractionCard
        interaction={{
          request_id: 'functions.ask_user:10',
          question: 'Need layout alignment',
          kind: 'ask_user',
          schema: {
            title: 'Layout check',
            questions: [
              {
                id: 'direction',
                header: 'Direction',
                question: 'Direction',
                type: 'single',
                options: [
                  { label: 'Option A', value: 'a' },
                  { label: 'Option B', value: 'b' },
                ],
              },
            ],
          },
        }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Other' })).toHaveStyle({ justifyContent: 'flex-start' })
  })
})
