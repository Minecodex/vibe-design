import fs from "node:fs/promises"
import path from "node:path"
import { spawn } from "node:child_process"
import { fileURLToPath } from "node:url"

import { getPhotoshopPluginPaths } from "./paths.mjs"

const currentDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(currentDir, "..")
const packageJson = JSON.parse(await fs.readFile(path.join(rootDir, "package.json"), "utf8"))
const paths = getPhotoshopPluginPaths(rootDir, packageJson.version)
const distDir = paths.distDir
const packageName = "canvas-photoshop-plugin.zip"
const stalePackageNames = [
  "canvas-photoshop-plugin.ccx",
  "Photoshop画布插件.ccx",
]
const releaseDir = paths.releaseDir
const publicLatestDir = paths.publicLatestDir
const publicVersionDir = paths.publicVersionDir

function runPowerShell(command) {
  return new Promise((resolve, reject) => {
    const child = spawn("powershell", ["-NoProfile", "-Command", command], { stdio: "inherit" })
    child.on("exit", (code) => {
      if (code === 0) {
        resolve()
        return
      }
      reject(new Error(`PowerShell exited with code ${code}`))
    })
  })
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true })
}

await ensureDir(releaseDir)
await ensureDir(publicLatestDir)
await ensureDir(publicVersionDir)

const releaseFile = path.join(releaseDir, packageName)
const latestFile = path.join(publicLatestDir, packageName)
const versionFile = path.join(publicVersionDir, packageName)

await fs.rm(releaseFile, { force: true })
await fs.rm(latestFile, { force: true })
await fs.rm(versionFile, { force: true })
for (const stalePackageName of stalePackageNames) {
  await fs.rm(path.join(releaseDir, stalePackageName), { force: true })
  await fs.rm(path.join(publicLatestDir, stalePackageName), { force: true })
  await fs.rm(path.join(publicVersionDir, stalePackageName), { force: true })
}

const escapedDistDir = distDir.replace(/'/g, "''")
const escapedReleaseFile = releaseFile.replace(/'/g, "''")
await runPowerShell(`Compress-Archive -Path '${escapedDistDir}\\*' -DestinationPath '${escapedReleaseFile}'`)
await fs.copyFile(releaseFile, latestFile)
await fs.copyFile(releaseFile, versionFile)

console.log(`Packaged Photoshop UXP plugin to ${releaseFile}`)
