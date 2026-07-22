import { Workbook } from 'exceljs'

interface LoadExceljsWorkbookOptions {
  base64: string
  fileName?: string | null
  mimeType?: string | null
}

function decodeBase64(base64: string): Uint8Array {
  if (typeof Buffer !== 'undefined') {
    return Uint8Array.from(Buffer.from(base64, 'base64'))
  }

  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}

function decodeBase64Text(base64: string): string {
  return new TextDecoder('utf-8').decode(decodeBase64(base64))
}

function getFileExtension(fileName: string | null | undefined): string {
  const normalized = String(fileName || '').trim().toLowerCase()
  return normalized.includes('.') ? normalized.slice(normalized.lastIndexOf('.') + 1) : ''
}

function inferWorkbookKind(options: LoadExceljsWorkbookOptions): 'csv' | 'xlsx' {
  const extension = getFileExtension(options.fileName)
  if (extension === 'csv' || options.mimeType === 'text/csv') {
    return 'csv'
  }
  return 'xlsx'
}

function inferSheetName(fileName: string | null | undefined): string {
  const normalized = String(fileName || '').trim()
  if (!normalized) {
    return 'Sheet1'
  }

  const fileStem = normalized.replace(/^.*[\\/]/, '').replace(/\.[^.]+$/, '').trim()
  return fileStem || 'Sheet1'
}

function parseCsvLine(line: string): string[] {
  const values: string[] = []
  let current = ''
  let inQuotes = false

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index]
    const nextCharacter = line[index + 1]

    if (character === '"') {
      if (inQuotes && nextCharacter === '"') {
        current += '"'
        index += 1
      } else {
        inQuotes = !inQuotes
      }
      continue
    }

    if (character === ',' && !inQuotes) {
      values.push(current)
      current = ''
      continue
    }

    current += character
  }

  values.push(current)
  return values
}

function normalizeCsvValue(value: string): string | number | boolean | null {
  const trimmed = value.trim()
  if (trimmed === '') {
    return ''
  }
  if (trimmed === 'true') {
    return true
  }
  if (trimmed === 'false') {
    return false
  }

  const numeric = Number(trimmed)
  if (!Number.isNaN(numeric) && trimmed !== '') {
    return numeric
  }

  return value
}

async function loadCsvWorkbook(base64: string, fileName?: string | null): Promise<Workbook> {
  const workbook = new Workbook()
  const worksheet = workbook.addWorksheet(inferSheetName(fileName))
  const text = decodeBase64Text(base64).replace(/^\uFEFF/, '')
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
  const contentLines = lines.filter((line, index) => line.length > 0 || index < lines.length - 1)

  for (const line of contentLines) {
    if (line === '' && contentLines.length === 1) {
      continue
    }
    worksheet.addRow(parseCsvLine(line).map(normalizeCsvValue))
  }

  return workbook
}

export async function loadExceljsWorkbook(options: LoadExceljsWorkbookOptions): Promise<Workbook> {
  if (inferWorkbookKind(options) === 'csv') {
    return loadCsvWorkbook(options.base64, options.fileName)
  }

  const workbook = new Workbook()
  await workbook.xlsx.load(decodeBase64(options.base64) as any)
  return workbook
}

export async function loadExceljsWorkbookFromBase64(base64: string): Promise<Workbook> {
  return loadExceljsWorkbook({ base64 })
}
