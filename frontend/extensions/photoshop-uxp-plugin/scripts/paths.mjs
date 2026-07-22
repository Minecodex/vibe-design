import path from "node:path"

export function getPhotoshopPluginPaths(pluginRoot, version) {
  const rootDir = path.resolve(pluginRoot)
  const frontendRoot = path.resolve(rootDir, "..", "..")
  const repoRoot = path.resolve(frontendRoot, "..")

  return {
    rootDir,
    frontendRoot,
    repoRoot,
    distDir: path.join(rootDir, "dist"),
    srcDir: path.join(rootDir, "src"),
    releaseDir: path.join(rootDir, "release"),
    publicLatestDir: path.join(frontendRoot, "public", "downloads", "photoshop-uxp", "latest"),
    publicVersionDir: path.join(frontendRoot, "public", "downloads", "photoshop-uxp", `v${version}`),
    envPath: path.join(repoRoot, ".env"),
  }
}
