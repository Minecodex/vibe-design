import {
  useEffect,
  useRef,
} from 'react'
import { useTranslation } from 'react-i18next'

import { createUniver } from '@univerjs/presets'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import '@univerjs/preset-sheets-core/lib/index.css'

import {
  type HomeChatOfficeSheetSnapshot,
} from './homeChatOfficeSnapshots'
import { resolveSheetUniverLocale } from './homeChatUniverSheetLocale'
import {
  toUniverWorkbookData,
} from './univerSheetToWorkbookPayload'

interface HomeChatUniverSheetEditorProps {
  snapshot?: HomeChatOfficeSheetSnapshot | null
  isDark?: boolean
}

function ensureResizeObserver() {
  if (typeof window === 'undefined' || typeof window.ResizeObserver !== 'undefined') {
    return
  }

  class NoopResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  (window as typeof window & { ResizeObserver: typeof ResizeObserver }).ResizeObserver =
    NoopResizeObserver as unknown as typeof ResizeObserver
}

export function HomeChatUniverSheetEditor({ snapshot, isDark = false }: HomeChatUniverSheetEditorProps) {
    const { i18n } = useTranslation()
    const containerRef = useRef<HTMLDivElement | null>(null)

    useEffect(() => {
      ensureResizeObserver()
      if (!containerRef.current) {
        return
      }

      containerRef.current.innerHTML = ''
      const univerLocale = resolveSheetUniverLocale(i18n.language)
      const { univerAPI } = createUniver({
        ...univerLocale,
        darkMode: isDark,
        presets: [
          UniverSheetsCorePreset({
            container: containerRef.current,
            header: false,
            toolbar: false,
            formulaBar: false,
            footer: true,
            contextMenu: false,
            sheets: {
              disableEdit: true,
            },
          } as any),
        ],
      })

      const workbookPayload = toUniverWorkbookData(snapshot)
      univerAPI.createWorkbook((workbookPayload || {}))
      const resizeFrame = window.requestAnimationFrame(() => {
        window.dispatchEvent(new Event('resize'))
      })

      return () => {
        window.cancelAnimationFrame(resizeFrame)
        univerAPI.dispose?.()
      }
    }, [i18n.language, isDark, snapshot])

    return (
      <div
        data-testid="home-chat-univer-sheet-editor"
        className="relative h-full min-h-0 w-full overflow-hidden bg-white"
      >
        <div ref={containerRef} className="absolute inset-0 min-h-0 w-full" />
      </div>
    )
}
