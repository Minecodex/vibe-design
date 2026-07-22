import fs from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { getPhotoshopPluginPaths } from "./paths.mjs"

const currentDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(currentDir, "..")
const paths = getPhotoshopPluginPaths(rootDir, "0.0.0")
const distDir = paths.distDir
const srcDir = paths.srcDir

function parseEnvFile(content) {
  return Object.fromEntries(
    content
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#") && line.includes("="))
      .map((line) => {
        const separatorIndex = line.indexOf("=")
        const key = line.slice(0, separatorIndex).trim()
        const rawValue = line.slice(separatorIndex + 1).trim()
        const value = rawValue.replace(/^['"]|['"]$/g, "")
        return [key, value]
      }),
  )
}

function normalizeServerOrigin(value) {
  const normalized = String(value || "").trim().replace(/\/+$/, "")
  return normalized.replace(/\/api\/v1$/i, "")
}

async function readRootEnv() {
  try {
    return parseEnvFile(await fs.readFile(paths.envPath, "utf8"))
  } catch {
    return {}
  }
}

const rootEnv = await readRootEnv()
const apiBaseUrl = normalizeServerOrigin(
  process.env.PHOTOSHOP_PLUGIN_API_BASE_URL
    || process.env.APP_API_BASE_URL
    || rootEnv.PHOTOSHOP_PLUGIN_API_BASE_URL
    || rootEnv.APP_API_BASE_URL
    || "http://localhost:8000",
)

async function ensureCleanDir(dir) {
  await fs.rm(dir, { recursive: true, force: true })
  await fs.mkdir(dir, { recursive: true })
}

async function copyDir(sourceDir, targetDir) {
  await fs.mkdir(targetDir, { recursive: true })
  const entries = await fs.readdir(sourceDir, { withFileTypes: true })
  for (const entry of entries) {
    const sourcePath = path.join(sourceDir, entry.name)
    const targetPath = path.join(targetDir, entry.name)
    if (entry.isDirectory()) {
      await copyDir(sourcePath, targetPath)
      continue
    }
    const content = await fs.readFile(sourcePath, "utf8")
    const nextContent = content.replaceAll("__API_BASE_URL__", apiBaseUrl)
    await fs.writeFile(targetPath, nextContent, "utf8")
  }
}

async function buildManifest() {
  const templatePath = path.join(rootDir, "manifest.template.json")
  const manifest = await fs.readFile(templatePath, "utf8")
  await fs.writeFile(
    path.join(distDir, "manifest.json"),
    manifest.replaceAll("__API_BASE_URL__", apiBaseUrl),
    "utf8",
  )
}

await ensureCleanDir(distDir)
await copyDir(srcDir, distDir)
await buildManifest()
console.log(`Built Photoshop UXP plugin to ${distDir}`)
