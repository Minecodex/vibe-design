import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SkillLibraryButton } from './SkillLibraryButton'
import { CHAT_SKILLS } from './chatSkills'

const skills = CHAT_SKILLS.map((skill) => ({
  ...skill,
  name: `${skill.id}-name`,
}))

describe('SkillLibraryButton', () => {
  const plugins = [
    {
      id: 'prompt_extractor',
      title: '提取插件',
      description: '下载并安装提取插件',
      actionLabel: '打开提取插件说明',
    },
    {
      id: 'photoshop_uxp',
      title: 'Photoshop 插件',
      description: '下载并安装 Photoshop UXP 插件',
      actionLabel: '打开 Photoshop 插件说明',
    },
  ] as const

  it('defaults to the skills tab when the tools panel opens', async () => {
    render(
      <SkillLibraryButton
        isDark={false}
        open
        showPluginsTab
        activeSkillId={null}
        skills={skills}
        buttonLabel="工具"
        panelTitle="工具"
        clearLabel="清除当前技能"
        skillsTabLabel="技能"
        pluginsTabLabel="插件"
        plugins={plugins}
        onToggle={vi.fn()}
        onSelect={vi.fn()}
        onClear={vi.fn()}
      />,
    )

    expect(screen.getByRole('tab', { name: '技能' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: `${skills[0].id}-name` })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '打开插件说明' })).not.toBeInTheDocument()
  })

  it('opens the prompt extractor modal from the plugins tab', async () => {
    render(
      <SkillLibraryButton
        isDark={false}
        open
        showPluginsTab
        activeSkillId={null}
        skills={skills}
        buttonLabel="工具"
        panelTitle="工具"
        clearLabel="清除当前技能"
        skillsTabLabel="技能"
        pluginsTabLabel="插件"
        plugins={plugins}
        onToggle={vi.fn()}
        onSelect={vi.fn()}
        onClear={vi.fn()}
      />,
    )

    await userEvent.click(screen.getByRole('tab', { name: '插件' }))
    await userEvent.click(screen.getByRole('button', { name: '打开提取插件说明' }))

    expect(screen.getByRole('heading', { name: '安装提取插件' })).toBeInTheDocument()
  })

  it('opens the photoshop plugin modal from the plugins tab', async () => {
    render(
      <SkillLibraryButton
        isDark={false}
        open
        showPluginsTab
        activeSkillId={null}
        skills={skills}
        buttonLabel="工具"
        panelTitle="工具"
        clearLabel="清除当前技能"
        skillsTabLabel="技能"
        pluginsTabLabel="插件"
        plugins={plugins}
        onToggle={vi.fn()}
        onSelect={vi.fn()}
        onClear={vi.fn()}
      />,
    )

    await userEvent.click(screen.getByRole('tab', { name: '插件' }))
    await userEvent.click(screen.getByRole('button', { name: '打开 Photoshop 插件说明' }))

    expect(screen.getByRole('heading', { name: '安装 Photoshop 插件' })).toBeInTheDocument()
  })

  it('forwards skill selection from the skills tab', async () => {
    const onSelect = vi.fn()

    render(
      <SkillLibraryButton
        isDark={false}
        open
        showPluginsTab
        activeSkillId={null}
        skills={skills}
        buttonLabel="工具"
        panelTitle="工具"
        clearLabel="清除当前技能"
        skillsTabLabel="技能"
        pluginsTabLabel="插件"
        plugins={plugins}
        onToggle={vi.fn()}
        onSelect={onSelect}
        onClear={vi.fn()}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: `${skills[0].id}-name` }))

    expect(onSelect).toHaveBeenCalledWith(skills[0].id)
  })

  it('hides the plugins tab when plugin capability is unavailable', () => {
    render(
      <SkillLibraryButton
        isDark={false}
        open
        showPluginsTab={false}
        activeSkillId={null}
        skills={skills}
        buttonLabel="工具"
        panelTitle="工具"
        clearLabel="清除当前技能"
        skillsTabLabel="技能"
        pluginsTabLabel="插件"
        plugins={plugins}
        onToggle={vi.fn()}
        onSelect={vi.fn()}
        onClear={vi.fn()}
      />,
    )

    expect(screen.getByRole('tab', { name: '技能' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '插件' })).not.toBeInTheDocument()
  })
})
