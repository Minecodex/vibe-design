import { LocaleType, mergeLocales } from '@univerjs/presets'

import UniverPresetDocsCoreEnUS from '@univerjs/preset-docs-core/locales/en-US'
import UniverPresetDocsCoreZhCN from '@univerjs/preset-docs-core/locales/zh-CN'
import UniverPresetSheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US'
import UniverPresetSheetsCoreZhCN from '@univerjs/preset-sheets-core/locales/zh-CN'

function resolveLocaleType(language?: string | null) {
  const normalized = String(language || '').trim().toLowerCase()
  return normalized.startsWith('zh') ? LocaleType.ZH_CN : LocaleType.EN_US
}

export function resolveSheetUniverLocale(language?: string | null) {
  const locale = resolveLocaleType(language)

  return {
    locale,
    locales: {
      [LocaleType.EN_US]: mergeLocales(UniverPresetDocsCoreEnUS, UniverPresetSheetsCoreEnUS),
      [LocaleType.ZH_CN]: mergeLocales(UniverPresetDocsCoreZhCN, UniverPresetSheetsCoreZhCN),
    },
  }
}
