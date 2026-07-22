import type { WorkspaceFileRead } from '@/api/endpoints/agent'
import { getApiBaseUrl } from '@/config/runtimeConfig'
import { isSessionHtmlFile } from './homeChatWorkspaceFileKinds'

export type ExternalOpenTarget =
  | { kind: 'office'; protocolUrl: string }
  | { kind: 'wps-sdk'; command: WpsSdkOpenCommand }
  | { kind: 'browser'; url: string }
  | { kind: 'unsupported' }
export type ExternalOpenSuite = 'office' | 'wps' | 'browser'

type WpsSdkClientType = 'wps' | 'et' | 'wpp'
const WPS_ADDIN_VERSION = '1.0.3'

interface WpsSdkOpenCommand {
  clientType: WpsSdkClientType
  addonName: string
  addinUrl: string
  jsPluginsXml: string
  param: Array<{
    name: 'OpenDoc'
    params: string
  }>
}

interface ExternalOpenDispatchers {
  openBrowser?: (url?: string | URL, target?: string, features?: string) => Window | null
  openProtocol?: (url: string) => void
  openWpsSdk?: (command: WpsSdkOpenCommand) => Promise<boolean>
  loadWpsSdk?: () => Promise<WpsRpcSdk>
}

interface WpsRpcSdk {
  WpsAddonMgr?: {
    enable?: (
      config: {
        name: string
        addonType: WpsSdkClientType
        online: 'true'
        url: string
        version: string
      },
      callback: (response: unknown) => void,
    ) => void
  }
  WpsInvoke?: {
    ClientType?: Record<WpsSdkClientType, WpsSdkClientType>
    InvokeAsHttp?: (
      clientType: WpsSdkClientType,
      name: string,
      func: string,
      param: WpsSdkOpenCommand['param'],
      callback: (response: unknown) => void,
      showToFront?: boolean,
      jsPluginsXml?: string,
      silentMode?: boolean,
      timeout?: number,
    ) => string | undefined
  }
}

function getFileExtension(file: Pick<WorkspaceFileRead, 'name' | 'path'>): string {
  return String(file.name || file.path || '').split('.').pop()?.toLowerCase() || ''
}

function getOfficeFileKind(file: Pick<WorkspaceFileRead, 'name' | 'path' | 'type' | 'artifact_kind' | 'artifact_metadata'>): 'document' | 'sheet' | 'presentation' | 'html' | null {
  const extension = getFileExtension(file)

  if (['doc', 'docx'].includes(extension)) {
    return 'document'
  }
  if (['xls', 'xlsx'].includes(extension)) {
    return 'sheet'
  }
  if (['ppt', 'pptx'].includes(extension)) {
    return 'presentation'
  }
  if (isSessionHtmlFile(file) || ['html', 'htm'].includes(extension)) {
    return 'html'
  }

  return null
}

function buildOfficeUriSchemeProtocolUrl(
  scheme: 'ms-word' | 'ms-excel' | 'ms-powerpoint',
  command: 'ofv' | 'ofe',
  accessibleFileUrl: string,
): string {
  return `${scheme}:${command}|u|${encodeURI(accessibleFileUrl)}`
}

function getWpsAddinManifestUrl(): string {
  return `${getApiBaseUrl()}/agent/harness/wps-addin/jsplugins.xml`
}

function getWpsAddinUrl(addonName: string): string {
  return `${getApiBaseUrl()}/agent/harness/wps-addin/${addonName}/`
}

const WPS_SDK_OPEN_FUNCTIONS: Record<Exclude<ReturnType<typeof getOfficeFileKind>, 'html' | null>, {
  clientType: WpsSdkClientType
  addonName: string
}> = {
  document: {
    clientType: 'wps',
    addonName: 'WpsOAAssist',
  },
  sheet: {
    clientType: 'et',
    addonName: 'EtOAAssist',
  },
  presentation: {
    clientType: 'wpp',
    addonName: 'WppOAAssist',
  },
}

function buildWpsSdkOpenCommand(
  kind: Exclude<ReturnType<typeof getOfficeFileKind>, 'html' | null>,
  accessibleFileUrl: string,
): WpsSdkOpenCommand {
  const config = WPS_SDK_OPEN_FUNCTIONS[kind]
  return {
    clientType: config.clientType,
    addonName: config.addonName,
    addinUrl: getWpsAddinUrl(config.addonName),
    jsPluginsXml: getWpsAddinManifestUrl(),
    param: [
      {
        name: 'OpenDoc',
        params: accessibleFileUrl,
      },
    ],
  }
}

export function buildExternalOpenTarget(
  file: Pick<WorkspaceFileRead, 'name' | 'path' | 'type' | 'artifact_kind' | 'artifact_metadata'>,
  accessibleFileUrl: string,
  suite: ExternalOpenSuite = 'office',
): ExternalOpenTarget {
  const kind = getOfficeFileKind(file)

  if (kind === 'html') {
    return { kind: 'browser', url: accessibleFileUrl }
  }
  if (suite === 'wps' && kind) {
    return {
      kind: 'wps-sdk',
      command: buildWpsSdkOpenCommand(kind, accessibleFileUrl),
    }
  }
  if (kind === 'document') {
    return {
      kind: 'office',
      protocolUrl: buildOfficeUriSchemeProtocolUrl('ms-word', 'ofv', accessibleFileUrl),
    }
  }
  if (kind === 'sheet') {
    return {
      kind: 'office',
      protocolUrl: buildOfficeUriSchemeProtocolUrl('ms-excel', 'ofv', accessibleFileUrl),
    }
  }
  if (kind === 'presentation') {
    return {
      kind: 'office',
      protocolUrl: buildOfficeUriSchemeProtocolUrl('ms-powerpoint', 'ofe', accessibleFileUrl),
    }
  }

  return { kind: 'unsupported' }
}

export function getExternalOpenSuites(file: Pick<WorkspaceFileRead, 'name' | 'path' | 'type' | 'artifact_kind' | 'artifact_metadata'>): ExternalOpenSuite[] {
  const kind = getOfficeFileKind(file)
  if (kind === 'html') {
    return ['browser']
  }
  if (kind) {
    return ['office', 'wps']
  }
  return []
}

export function isExternalOpenSupported(file: Pick<WorkspaceFileRead, 'name' | 'path' | 'type' | 'artifact_kind' | 'artifact_metadata'>): boolean {
  return getExternalOpenSuites(file).length > 0
}

export function openExternalTarget(
  target: ExternalOpenTarget,
  dispatchers: ExternalOpenDispatchers = {},
): Promise<boolean> {
  if (target.kind === 'unsupported') {
    return Promise.resolve(false)
  }

  if (target.kind === 'browser') {
    const openBrowser = dispatchers.openBrowser || window.open.bind(window)
    openBrowser(target.url, '_blank', 'noopener,noreferrer')
    return Promise.resolve(true)
  }

  if (target.kind === 'wps-sdk') {
    const openWpsSdk = dispatchers.openWpsSdk || ((command) => openWpsSdkTarget(command, dispatchers.loadWpsSdk))
    return openWpsSdk(target.command)
  }

  const openProtocol = dispatchers.openProtocol || ((url: string) => {
    window.location.href = url
  })
  openProtocol(target.protocolUrl)
  return Promise.resolve(true)
}

async function loadWpsRpcSdk(): Promise<WpsRpcSdk> {
  const existingSdk = window as Window & {
    WpsAddonMgr?: WpsRpcSdk['WpsAddonMgr']
    WpsInvoke?: WpsRpcSdk['WpsInvoke']
  }
  const existingInvoke = existingSdk.WpsInvoke
  if (existingInvoke) {
    return {
      WpsAddonMgr: existingSdk.WpsAddonMgr,
      WpsInvoke: existingInvoke,
    }
  }

  const imported = await import('wpsjs-rpc-sdk') as WpsRpcSdk & { default?: WpsRpcSdk }
  return imported.default || imported
}

async function openWpsSdkTarget(command: WpsSdkOpenCommand, loadSdk = loadWpsRpcSdk): Promise<boolean> {
  const sdk = await loadSdk()
  const invokeAsHttp = sdk.WpsInvoke?.InvokeAsHttp
  if (!invokeAsHttp) {
    throw new Error('WPS SDK InvokeAsHttp is unavailable')
  }

  await enableWpsAddin(command, sdk)

  return new Promise<boolean>((resolve, reject) => {
    let settled = false
    const timeoutId = window.setTimeout(() => {
      if (settled) {
        return
      }
      settled = true
      reject(new Error('WPS SDK open timed out'))
    }, 15000)

    const complete = (success: boolean, error?: Error) => {
      if (settled) {
        return
      }
      settled = true
      window.clearTimeout(timeoutId)
      if (success) {
        resolve(true)
      } else {
        reject(error || new Error('WPS SDK open failed'))
      }
    }

    try {
      const immediateError = invokeAsHttp(
        getWpsSdkClientType(sdk, command.clientType),
        command.addonName,
        'dispatcher',
        command.param,
        (response) => {
          const maybeResponse = response as { status?: number; message?: string; response?: string }
          complete(
            maybeResponse.status === 0,
            new Error(maybeResponse.message || maybeResponse.response || 'WPS SDK open failed'),
          )
        },
        true,
        command.jsPluginsXml,
        false,
        15000,
      )

      if (immediateError) {
        complete(false, new Error(immediateError))
      }
    } catch (error) {
      complete(false, error instanceof Error ? error : new Error('WPS SDK open failed'))
    }
  })
}

function getWpsSdkClientType(sdk: WpsRpcSdk, clientType: WpsSdkClientType): WpsSdkClientType {
  return sdk.WpsInvoke?.ClientType?.[clientType] || clientType
}

function enableWpsAddin(command: WpsSdkOpenCommand, sdk: WpsRpcSdk): Promise<void> {
  const enable = sdk.WpsAddonMgr?.enable
  if (!enable) {
    return Promise.resolve()
  }

  return new Promise<void>((resolve, reject) => {
    try {
      enable(
        {
          name: command.addonName,
          addonType: getWpsSdkClientType(sdk, command.clientType),
          online: 'true',
          url: command.addinUrl,
          version: WPS_ADDIN_VERSION,
        },
        (response) => {
          const maybeResponse = response as { status?: number; message?: string; msg?: string; response?: string }
          if (maybeResponse.status === 0) {
            resolve()
            return
          }
          reject(new Error(maybeResponse.message || maybeResponse.msg || maybeResponse.response || 'WPS add-in install failed'))
        },
      )
    } catch (error) {
      reject(error instanceof Error ? error : new Error('WPS add-in install failed'))
    }
  })
}
