const assert = require("node:assert/strict")
const path = require("node:path")
const { pathToFileURL } = require("node:url")

async function main() {
  const { getPhotoshopPluginPaths } = await import(
    pathToFileURL(path.resolve(__dirname, "../scripts/paths.mjs"))
  )

  const pluginRoot = path.resolve(__dirname, "..")
  const frontendRoot = path.resolve(pluginRoot, "..", "..")
  const repoRoot = path.resolve(frontendRoot, "..")
  const paths = getPhotoshopPluginPaths(pluginRoot, "0.1.21")

  assert.equal(paths.repoRoot, repoRoot)
  assert.equal(paths.frontendRoot, frontendRoot)
  assert.equal(paths.distDir, path.join(pluginRoot, "dist"))
  assert.equal(paths.srcDir, path.join(pluginRoot, "src"))
  assert.equal(paths.releaseDir, path.join(pluginRoot, "release"))
  assert.equal(
    paths.publicLatestDir,
    path.join(frontendRoot, "public", "downloads", "photoshop-uxp", "latest"),
  )
  assert.equal(
    paths.publicVersionDir,
    path.join(frontendRoot, "public", "downloads", "photoshop-uxp", "v0.1.21"),
  )
  assert.equal(paths.envPath, path.join(repoRoot, ".env"))
}

main()
