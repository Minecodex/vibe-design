import { createInstance } from 'i18next'

export function createTranslationFixture(resources: Record<string, string> = {}) {
  const instance = createInstance()
  void instance.init({
    lng: 'en', fallbackLng: 'en', keySeparator: false, initImmediate: false,
    resources: { en: { translation: resources } },
  })
  return instance.getFixedT('en')
}
