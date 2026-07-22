import { describe, expect, it, vi } from 'vitest'

import { buildExternalOpenTarget, getExternalOpenSuites, openExternalTarget } from './homeChatExternalOpen'

describe('buildExternalOpenTarget', () => {
  it.each([
    ['brief.docx', 'ms-word:ofv|u|https://example.com/preview-files/brief.docx?preview_token=abc'],
    ['budget.xlsx', 'ms-excel:ofv|u|https://example.com/preview-files/budget.xlsx?preview_token=abc'],
    ['deck.pptx', 'ms-powerpoint:ofe|u|https://example.com/preview-files/deck.pptx?preview_token=abc'],
  ])('builds an Office protocol URL for %s', (name, expected) => {
    expect(buildExternalOpenTarget(
      { name, path: name, type: 'other' },
      `https://example.com/preview-files/${name}?preview_token=abc`,
    )).toEqual({ kind: 'office', protocolUrl: expected })
  })

  it.each([
    ['brief.docx', 'wps', 'WpsOAAssist'],
    ['budget.xlsx', 'et', 'EtOAAssist'],
    ['deck.pptx', 'wpp', 'WppOAAssist'],
  ])('builds a WPS OA assistant SDK command for %s', (name, clientType, addonName) => {
    const url = `https://example.com/preview-files/${name}?preview_token=abc`
    expect(buildExternalOpenTarget(
      { name, path: name, type: 'other' },
      url,
      'wps',
    )).toEqual({
      kind: 'wps-sdk',
      command: {
        clientType,
        addonName,
        addinUrl: `http://localhost:8000/api/v1/agent/harness/wps-addin/${addonName}/`,
        jsPluginsXml: 'http://localhost:8000/api/v1/agent/harness/wps-addin/jsplugins.xml',
        param: [
          {
            name: 'OpenDoc',
            params: url,
          },
        ],
      },
    })
  })

  it('returns a browser URL for html files', () => {
    expect(buildExternalOpenTarget(
      { name: 'landing.html', path: 'landing.html', type: 'other' },
      'https://example.com/preview-html/landing.html?preview_token=abc',
    )).toEqual({
      kind: 'browser',
      url: 'https://example.com/preview-html/landing.html?preview_token=abc',
    })
  })

  it('returns a browser URL for web_bundle zip files', () => {
    expect(buildExternalOpenTarget(
      {
        name: 'index.zip',
        path: 'published/f_site/v0001/source.zip',
        type: 'web',
        artifact_kind: 'web_bundle',
        artifact_metadata: {
          artifact_kind: 'web_bundle',
          bundle_format: 'zip',
          entry: 'index.html',
        },
      },
      'https://example.com/preview-html-version/f_site/v0001?preview_token=abc',
    )).toEqual({
      kind: 'browser',
      url: 'https://example.com/preview-html-version/f_site/v0001?preview_token=abc',
    })
  })

  it('returns unsupported for unknown file types', () => {
    expect(buildExternalOpenTarget(
      { name: 'notes.md', path: 'notes.md', type: 'text' },
      'https://example.com/preview-files/notes.md?preview_token=abc',
    )).toEqual({ kind: 'unsupported' })
  })

  it('does not treat markdown files as Office documents when the upstream type is document', () => {
    expect(getExternalOpenSuites({
      name: 'notes.md',
      path: 'work/notes.md',
      type: 'document',
    })).toEqual([])

    expect(buildExternalOpenTarget(
      { name: 'notes.md', path: 'work/notes.md', type: 'document' },
      'https://example.com/preview-files/notes.md?preview_token=abc',
    )).toEqual({ kind: 'unsupported' })
  })

  it('offers Office and WPS suites for office-like files', () => {
    expect(getExternalOpenSuites({ name: 'deck.pptx', path: 'deck.pptx', type: 'other' })).toEqual([
      'office',
      'wps',
    ])
  })

  it('offers only browser open for html files', () => {
    expect(getExternalOpenSuites({ name: 'landing.html', path: 'landing.html', type: 'other' })).toEqual([
      'browser',
    ])
  })

  it('offers only browser open for web_bundle zip files', () => {
    expect(getExternalOpenSuites({
      name: 'index.zip',
      path: 'published/f_site/v0001/source.zip',
      type: 'web',
      artifact_kind: 'web_bundle',
      artifact_metadata: {
        artifact_kind: 'web_bundle',
        bundle_format: 'zip',
        entry: 'index.html',
      },
    })).toEqual([
      'browser',
    ])
  })

  it('dispatches Office protocol targets through the protocol opener', async () => {
    const openBrowser = vi.fn()
    const openProtocol = vi.fn()

    await expect(openExternalTarget(
      { kind: 'office', protocolUrl: 'ms-word:ofv|u|https://example.com/spec.docx' },
      { openBrowser, openProtocol },
    )).resolves.toBe(true)

    expect(openProtocol).toHaveBeenCalledWith('ms-word:ofv|u|https://example.com/spec.docx')
    expect(openBrowser).not.toHaveBeenCalled()
  })

  it('dispatches WPS SDK targets through the SDK opener', async () => {
    const openProtocol = vi.fn()
    const openWpsSdk = vi.fn().mockResolvedValue(true)
    const command = {
      clientType: 'wps' as const,
      addonName: 'WpsOAAssist',
      addinUrl: 'http://localhost:8000/api/v1/agent/harness/wps-addin/WpsOAAssist/',
      jsPluginsXml: 'http://localhost:8000/api/v1/agent/harness/wps-addin/jsplugins.xml',
      param: [
        {
          name: 'OpenDoc' as const,
          params: 'https://example.com/spec.docx',
        },
      ],
    }

    await expect(openExternalTarget(
      { kind: 'wps-sdk', command },
      { openProtocol, openWpsSdk },
    )).resolves.toBe(true)

    expect(openWpsSdk).toHaveBeenCalledWith(command)
    expect(openProtocol).not.toHaveBeenCalled()
  })

  it('installs the WPS add-in before invoking it through the default SDK opener', async () => {
    const invokeAsHttp = vi.fn((_clientType, _name, _func, _param, callback) => {
      callback({ status: 0, response: '{}' })
      return undefined
    })
    const enable = vi.fn((_config, callback) => {
      callback({ status: 0, response: 'ok' })
    })

    await expect(openExternalTarget(
      {
        kind: 'wps-sdk',
        command: {
          clientType: 'et',
          addonName: 'EtOAAssist',
          addinUrl: 'http://localhost:8000/api/v1/agent/harness/wps-addin/EtOAAssist/',
          jsPluginsXml: 'http://localhost:8000/api/v1/agent/harness/wps-addin/jsplugins.xml',
          param: [
            {
              name: 'OpenDoc',
              params: 'https://example.com/budget.xlsx',
            },
          ],
        },
      },
      {
        loadWpsSdk: async () => ({
          WpsAddonMgr: { enable },
          WpsInvoke: { InvokeAsHttp: invokeAsHttp },
        }),
      },
    )).resolves.toBe(true)

    expect(enable).toHaveBeenCalledWith({
      name: 'EtOAAssist',
      addonType: 'et',
      online: 'true',
      url: 'http://localhost:8000/api/v1/agent/harness/wps-addin/EtOAAssist/',
      version: '1.0.3',
    }, expect.any(Function))
    expect(invokeAsHttp).toHaveBeenCalled()
  })

  it('uses WPS SDK ClientType enum values when available', async () => {
    const invokeAsHttp = vi.fn((_clientType, _name, _func, _param, callback) => {
      callback({ status: 0, response: '{}' })
      return undefined
    })
    const enable = vi.fn((_config, callback) => {
      callback({ status: 0, response: 'ok' })
    })

    await expect(openExternalTarget(
      {
        kind: 'wps-sdk',
        command: {
          clientType: 'wpp',
          addonName: 'WppOAAssist',
          addinUrl: 'http://localhost:8000/api/v1/agent/harness/wps-addin/WppOAAssist/',
          jsPluginsXml: 'http://localhost:8000/api/v1/agent/harness/wps-addin/jsplugins.xml',
          param: [
            {
              name: 'OpenDoc',
              params: 'https://example.com/deck.pptx',
            },
          ],
        },
      },
      {
        loadWpsSdk: async () => ({
          WpsAddonMgr: { enable },
          WpsInvoke: {
            ClientType: { wps: 'wps', et: 'et', wpp: 'wpp' },
            InvokeAsHttp: invokeAsHttp,
          },
        }),
      },
    )).resolves.toBe(true)

    expect(enable).toHaveBeenCalledWith(expect.objectContaining({ addonType: 'wpp' }), expect.any(Function))
    expect(invokeAsHttp).toHaveBeenCalledWith(
      'wpp',
      'WppOAAssist',
      'dispatcher',
      expect.any(Object),
      expect.any(Function),
      true,
      'http://localhost:8000/api/v1/agent/harness/wps-addin/jsplugins.xml',
      false,
      15000,
    )
  })

  it('opens browser targets in a new tab', async () => {
    const openBrowser = vi.fn()
    const openProtocol = vi.fn()

    await expect(openExternalTarget(
      { kind: 'browser', url: 'https://example.com/preview-html/landing.html' },
      { openBrowser, openProtocol },
    )).resolves.toBe(true)

    expect(openBrowser).toHaveBeenCalledWith(
      'https://example.com/preview-html/landing.html',
      '_blank',
      'noopener,noreferrer',
    )
    expect(openProtocol).not.toHaveBeenCalled()
  })
})
