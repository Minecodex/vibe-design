import { useEffect, useState, type RefObject } from 'react'
import { Download, Wrench, X } from 'lucide-react'

import { PhotoshopPluginDownloadModal } from './components/PhotoshopPluginDownloadModal'
import { PromptExtractorDownloadModal } from './components/PromptExtractorDownloadModal'
import type { ChatSkillDefinition, ChatSkillId } from './chatSkills'

type ToolTabId = 'skills' | 'plugins'
type PluginModalId = 'prompt_extractor' | 'photoshop_uxp'

interface PluginCardDefinition {
  id: PluginModalId
  title: string
  description: string
  actionLabel: string
}

interface SkillLibraryButtonProps {
  isDark: boolean
  open: boolean
  showPluginsTab: boolean
  activeSkillId: string | null
  skills: Array<ChatSkillDefinition & { name: string }>
  buttonLabel: string
  panelTitle: string
  clearLabel: string
  skillsTabLabel: string
  pluginsTabLabel: string
  plugins: ReadonlyArray<PluginCardDefinition>
  onToggle: () => void
  onSelect: (skillId: ChatSkillId) => void
  onClear: () => void
  buttonRef?: RefObject<HTMLDivElement>
  panelRef?: RefObject<HTMLDivElement>
}

export function SkillLibraryButton({
  isDark,
  open,
  showPluginsTab,
  activeSkillId,
  skills,
  buttonLabel,
  panelTitle,
  clearLabel,
  skillsTabLabel,
  pluginsTabLabel,
  plugins,
  onToggle,
  onSelect,
  onClear,
  buttonRef,
  panelRef,
}: SkillLibraryButtonProps) {
  const [activeTab, setActiveTab] = useState<ToolTabId>('skills')
  const [activePluginModal, setActivePluginModal] = useState<PluginModalId | null>(null)

  useEffect(() => {
    if (open) {
      setActiveTab('skills')
    }
  }, [open])

  const tabButtonStyle = (tabId: ToolTabId) => ({
    flex: 1,
    height: 34,
    borderRadius: 999,
    border: 'none',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 700,
    transition: 'all 0.2s ease',
    backgroundColor:
      activeTab === tabId
        ? 'color-mix(in srgb, var(--app-primary) 14%, transparent)'
        : 'transparent',
    color:
      activeTab === tabId
        ? 'var(--app-primary)'
        : 'var(--app-foreground-muted)',
  })

  return (
    <>
      <div style={{ position: 'relative' }}>
        <div ref={buttonRef}>
          <button
            type="button"
            aria-label={buttonLabel}
            onClick={onToggle}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              height: 32,
              padding: '0 12px',
              borderRadius: 999,
              border: 'none',
              backgroundColor: 'color-mix(in srgb, var(--app-primary) 14%, transparent)',
              color: 'var(--app-primary)',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Wrench size={14} />
            </div>
            <span style={{ whiteSpace: 'nowrap' }}>{buttonLabel}</span>
          </button>
        </div>

        {open && (
          <div
            ref={panelRef}
            style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: 12,
              width: 320,
              padding: 16,
              borderRadius: 20,
              backgroundColor: 'var(--app-glass)',
              border: '1px solid var(--app-border)',
              boxShadow: 'var(--app-shadow-panel)',
              backdropFilter: 'var(--app-blur)',
              WebkitBackdropFilter: 'var(--app-blur)',
              zIndex: 1200,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--app-foreground)' }}>
                {panelTitle}
              </div>
              {activeTab === 'skills' && activeSkillId && (
                <button
                  type="button"
                  aria-label={clearLabel}
                  onClick={onClear}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    border: 'none',
                    backgroundColor: 'transparent',
                    color: 'var(--app-foreground-muted)',
                    cursor: 'pointer',
                  }}
                >
                  <X size={14} />
                </button>
              )}
            </div>

            <div
              role="tablist"
              aria-label={panelTitle}
              style={{
                display: 'flex',
                gap: 6,
                padding: 4,
                marginBottom: 14,
                borderRadius: 999,
                backgroundColor: 'var(--app-control-track)',
              }}
            >
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'skills'}
                onClick={() => setActiveTab('skills')}
                style={tabButtonStyle('skills')}
              >
                {skillsTabLabel}
              </button>
              {showPluginsTab ? (
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === 'plugins'}
                  onClick={() => setActiveTab('plugins')}
                  style={tabButtonStyle('plugins')}
                >
                  {pluginsTabLabel}
                </button>
              ) : null}
            </div>

            {activeTab === 'skills' || !showPluginsTab ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {skills.map((skill) => {
                  const Icon = skill.icon
                  const isActive = activeSkillId === skill.id

                  return (
                    <button
                      key={skill.id}
                      type="button"
                      aria-label={skill.name}
                      onClick={() => onSelect(skill.id)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 16,
                        width: '100%',
                        padding: '16px',
                        borderRadius: 20,
                        border: isActive ? `1.5px solid ${skill.color}88` : '1px solid var(--app-border)',
                        backgroundColor: isActive ? (isDark ? `${skill.color}15` : `${skill.color}05`) : 'var(--app-surface-muted)',
                        cursor: 'pointer',
                        textAlign: 'left',
                        transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                        boxShadow: isActive ? `0 8px 24px ${skill.color}15` : 'none',
                      }}
                    >
                      <div
                        style={{
                          width: 44,
                          height: 44,
                          borderRadius: 12,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: skill.color,
                          backgroundColor: isDark ? `${skill.color}22` : `${skill.color}11`,
                          flexShrink: 0,
                        }}
                      >
                        <Icon size={22} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--app-foreground)' }}>
                          {skill.name}
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {plugins.map((plugin) => (
                  <button
                    key={plugin.id}
                    type="button"
                    aria-label={plugin.actionLabel}
                    onClick={() => setActivePluginModal(plugin.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 14,
                      width: '100%',
                      padding: 16,
                      borderRadius: 20,
                      border: '1px solid var(--app-border)',
                      backgroundColor: 'var(--app-surface-muted)',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                    }}
                  >
                    <div
                      style={{
                        width: 44,
                        height: 44,
                        borderRadius: 12,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'var(--app-primary)',
                        backgroundColor: 'color-mix(in srgb, var(--app-primary) 14%, transparent)',
                        flexShrink: 0,
                      }}
                    >
                      <Download size={20} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--app-foreground)', marginBottom: 4 }}>
                        {plugin.title}
                      </div>
                      <div style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--app-foreground-muted)' }}>
                        {plugin.description}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <PromptExtractorDownloadModal
        open={activePluginModal === 'prompt_extractor'}
        onOpenChange={(open: boolean) => setActivePluginModal(open ? 'prompt_extractor' : null)}
      />
      <PhotoshopPluginDownloadModal
        open={activePluginModal === 'photoshop_uxp'}
        onOpenChange={(open: boolean) => setActivePluginModal(open ? 'photoshop_uxp' : null)}
      />
    </>
  )
}
