import { build } from 'vite'
import react from '@vitejs/plugin-react'
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ZIP_FILE_NAME = '提取插件.zip'
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const extensionRoot = path.resolve(__dirname, '..')
const defaultFrontendRoot = path.resolve(extensionRoot, '..', '..')

function toPosixPath(filePath) {
  return filePath.replace(/\\/g, '/')
}

function readManifest() {
  return JSON.parse(readFileSync(path.join(extensionRoot, 'manifest.json'), 'utf8'))
}

export function getPromptExtractorPackagingPlan(frontendRoot = defaultFrontendRoot) {
  const manifest = readManifest()
  const versionTag = `v${manifest.version}`
  const downloadRoot = path.join(frontendRoot, 'public', 'downloads', 'prompt-extractor')
  const stagingRoot = path.join(extensionRoot, '.package')

  return {
    manifest,
    zipFileName: ZIP_FILE_NAME,
    stagingRoot,
    extensionBuildDir: path.join(stagingRoot, 'extension'),
    versionedReleaseDir: path.join(downloadRoot, versionTag),
    latestReleaseDir: path.join(downloadRoot, 'latest'),
    versionedZipPath: path.join(downloadRoot, versionTag, ZIP_FILE_NAME),
    latestZipPath: path.join(downloadRoot, 'latest', ZIP_FILE_NAME),
  }
}

export function getPromptExtractorRuntimeDefine(defaultServer = '') {
  return {
    __PROMPT_EXTRACTOR_DEFAULT_SERVER__: JSON.stringify(defaultServer),
    'process.env.NODE_ENV': JSON.stringify('production'),
  }
}

export function getPromptExtractorRuntimeIntro() {
  return "const process = globalThis.process ?? { env: { NODE_ENV: 'production' } };"
}

function parseEnvFile(content) {
  return Object.fromEntries(
    content
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#') && line.includes('='))
      .map((line) => {
        const separatorIndex = line.indexOf('=')
        const key = line.slice(0, separatorIndex).trim()
        const rawValue = line.slice(separatorIndex + 1).trim()
        const value = rawValue.replace(/^['"]|['"]$/g, '')
        return [key, value]
      }),
  )
}

function normalizeServerOrigin(value) {
  const normalized = String(value || '').trim().replace(/\/+$/, '')
  return normalized.replace(/\/api\/v1$/i, '')
}

function readRootEnv(frontendRoot = defaultFrontendRoot) {
  const envPath = path.resolve(frontendRoot, '..', '.env')
  if (!existsSync(envPath)) {
    return {}
  }

  return parseEnvFile(readFileSync(envPath, 'utf8'))
}

export function resolvePromptExtractorDefaultServer(env = process.env) {
  return normalizeServerOrigin(
    env.PROMPT_EXTRACTOR_DEFAULT_SERVER
      || env.APP_API_BASE_URL
      || 'http://localhost:8000',
  )
}

async function buildEntry(entry, outfile, format, globalName, define = {}) {
  const outDir = path.dirname(outfile)
  mkdirSync(outDir, { recursive: true })

  await build({
    configFile: false,
    publicDir: false,
    plugins: [react()],
    define,
    build: {
      emptyOutDir: false,
      outDir,
      sourcemap: false,
      lib: {
        entry,
        formats: [format],
        name: globalName,
        fileName: () => path.basename(outfile),
      },
      rollupOptions: {
        output: {
          inlineDynamicImports: true,
          intro: getPromptExtractorRuntimeIntro(),
        },
      },
    },
  })
}

function writeHtmlShell(filePath, title, scriptFile) {
  writeFileSync(
    filePath,
    `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script src="./${scriptFile}"></script>
  </body>
</html>
`,
    'utf8',
  )
}

function collectFiles(rootDir, currentDir = rootDir) {
  const entries = readdirSync(currentDir, { withFileTypes: true })
  const files = []

  for (const entry of entries) {
    const absolutePath = path.join(currentDir, entry.name)
    if (entry.isDirectory()) {
      files.push(...collectFiles(rootDir, absolutePath))
      continue
    }

    files.push({
      absolutePath,
      relativePath: toPosixPath(path.relative(rootDir, absolutePath)),
    })
  }

  return files.sort((left, right) => left.relativePath.localeCompare(right.relativePath))
}

function createCrc32Table() {
  const table = new Uint32Array(256)
  for (let index = 0; index < 256; index += 1) {
    let value = index
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1)
    }
    table[index] = value >>> 0
  }
  return table
}

const crc32Table = createCrc32Table()

function crc32(buffer) {
  let value = 0xffffffff
  for (const byte of buffer) {
    value = crc32Table[(value ^ byte) & 0xff] ^ (value >>> 8)
  }
  return (value ^ 0xffffffff) >>> 0
}

function getDosTimestamp(date) {
  const safeYear = Math.max(date.getFullYear(), 1980)
  const dosTime =
    ((date.getHours() & 0x1f) << 11) |
    ((date.getMinutes() & 0x3f) << 5) |
    Math.floor(date.getSeconds() / 2)
  const dosDate =
    (((safeYear - 1980) & 0x7f) << 9) |
    (((date.getMonth() + 1) & 0x0f) << 5) |
    (date.getDate() & 0x1f)

  return { dosTime, dosDate }
}

function writeStoredZip(sourceDir, zipPath) {
  const files = collectFiles(sourceDir)
  const localChunks = []
  const centralChunks = []
  let offset = 0

  for (const file of files) {
    const content = readFileSync(file.absolutePath)
    const stats = statSync(file.absolutePath)
    const filenameBuffer = Buffer.from(file.relativePath, 'utf8')
    const checksum = crc32(content)
    const { dosTime, dosDate } = getDosTimestamp(stats.mtime)
    const generalPurposeFlag = 0x0800

    const localHeader = Buffer.alloc(30)
    localHeader.writeUInt32LE(0x04034b50, 0)
    localHeader.writeUInt16LE(20, 4)
    localHeader.writeUInt16LE(generalPurposeFlag, 6)
    localHeader.writeUInt16LE(0, 8)
    localHeader.writeUInt16LE(dosTime, 10)
    localHeader.writeUInt16LE(dosDate, 12)
    localHeader.writeUInt32LE(checksum, 14)
    localHeader.writeUInt32LE(content.length, 18)
    localHeader.writeUInt32LE(content.length, 22)
    localHeader.writeUInt16LE(filenameBuffer.length, 26)
    localHeader.writeUInt16LE(0, 28)
    localChunks.push(localHeader, filenameBuffer, content)

    const centralHeader = Buffer.alloc(46)
    centralHeader.writeUInt32LE(0x02014b50, 0)
    centralHeader.writeUInt16LE(20, 4)
    centralHeader.writeUInt16LE(20, 6)
    centralHeader.writeUInt16LE(generalPurposeFlag, 8)
    centralHeader.writeUInt16LE(0, 10)
    centralHeader.writeUInt16LE(dosTime, 12)
    centralHeader.writeUInt16LE(dosDate, 14)
    centralHeader.writeUInt32LE(checksum, 16)
    centralHeader.writeUInt32LE(content.length, 20)
    centralHeader.writeUInt32LE(content.length, 24)
    centralHeader.writeUInt16LE(filenameBuffer.length, 28)
    centralHeader.writeUInt16LE(0, 30)
    centralHeader.writeUInt16LE(0, 32)
    centralHeader.writeUInt16LE(0, 34)
    centralHeader.writeUInt16LE(0, 36)
    centralHeader.writeUInt32LE(0, 38)
    centralHeader.writeUInt32LE(offset, 42)
    centralChunks.push(centralHeader, filenameBuffer)

    offset += localHeader.length + filenameBuffer.length + content.length
  }

  const centralDirectory = Buffer.concat(centralChunks)
  const endRecord = Buffer.alloc(22)
  endRecord.writeUInt32LE(0x06054b50, 0)
  endRecord.writeUInt16LE(0, 4)
  endRecord.writeUInt16LE(0, 6)
  endRecord.writeUInt16LE(files.length, 8)
  endRecord.writeUInt16LE(files.length, 10)
  endRecord.writeUInt32LE(centralDirectory.length, 12)
  endRecord.writeUInt32LE(offset, 16)
  endRecord.writeUInt16LE(0, 20)

  writeFileSync(zipPath, Buffer.concat([...localChunks, centralDirectory, endRecord]))
}

export async function packagePromptExtractorExtension(frontendRoot = defaultFrontendRoot) {
  const plan = getPromptExtractorPackagingPlan(frontendRoot)
  const defaultServer = resolvePromptExtractorDefaultServer({
    ...readRootEnv(frontendRoot),
    ...process.env,
  })

  rmSync(plan.stagingRoot, { recursive: true, force: true })
  rmSync(plan.versionedReleaseDir, { recursive: true, force: true })
  rmSync(plan.latestReleaseDir, { recursive: true, force: true })
  mkdirSync(plan.extensionBuildDir, { recursive: true })
  mkdirSync(plan.versionedReleaseDir, { recursive: true })
  mkdirSync(plan.latestReleaseDir, { recursive: true })

  const define = getPromptExtractorRuntimeDefine(defaultServer)

  await buildEntry(
    path.join(extensionRoot, 'src', 'options.tsx'),
    path.join(plan.extensionBuildDir, 'options.js'),
    'iife',
    'PromptExtractorOptions',
    define,
  )
  await buildEntry(
    path.join(extensionRoot, 'src', 'result.tsx'),
    path.join(plan.extensionBuildDir, 'result.js'),
    'iife',
    'PromptExtractorResult',
    define,
  )
  await buildEntry(
    path.join(extensionRoot, 'src', 'background.ts'),
    path.join(plan.extensionBuildDir, 'background.js'),
    'es',
    'PromptExtractorBackground',
    define,
  )
  await buildEntry(
    path.join(extensionRoot, 'src', 'content.tsx'),
    path.join(plan.extensionBuildDir, 'content.js'),
    'iife',
    'PromptExtractorContent',
    define,
  )

  cpSync(path.join(extensionRoot, 'manifest.json'), path.join(plan.extensionBuildDir, 'manifest.json'))
  writeHtmlShell(path.join(plan.extensionBuildDir, 'options.html'), '提取插件设置', 'options.js')
  writeHtmlShell(path.join(plan.extensionBuildDir, 'result.html'), '提取提示词', 'result.js')

  writeStoredZip(plan.extensionBuildDir, plan.versionedZipPath)
  cpSync(plan.versionedZipPath, plan.latestZipPath)
  rmSync(plan.stagingRoot, { recursive: true, force: true })

  return plan
}

if (process.argv[1] && existsSync(process.argv[1]) && path.resolve(process.argv[1]) === __filename) {
  packagePromptExtractorExtension()
    .then((plan) => {
      process.stdout.write(`Packaged prompt extractor extension to ${plan.versionedZipPath}\n`)
      process.stdout.write(`Updated latest package at ${plan.latestZipPath}\n`)
    })
    .catch((error) => {
      process.stderr.write(`${error instanceof Error ? error.stack || error.message : String(error)}\n`)
      process.exitCode = 1
    })
}
