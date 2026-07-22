#!/usr/bin/env node
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const srcDir = path.join(root, 'src')

const patterns = [
  { name: 'neutral alpha utility class', regex: /\b(?:bg|border|text|ring|shadow)-(?:white|black|slate|gray|zinc|neutral)\/(?:\[[^\]]+\]|[0-9]+)/g },
  { name: 'opacity utility on app chrome', regex: /\bopacity-(?:[1-9][0-9]?|100)\b|\bopacity\s*:\s*(?:0?\.\d+|[01])\b/g },
  { name: 'text-[#...]', regex: /\btext-\[[^\]]*#[0-9a-fA-F]{3,8}[^\]]*\]/g },
  { name: 'bg-[#...]', regex: /\bbg-\[[^\]]*#[0-9a-fA-F]{3,8}[^\]]*\]/g },
  { name: 'border-[#...]', regex: /\bborder-\[[^\]]*#[0-9a-fA-F]{3,8}[^\]]*\]/g },
  {
    name: 'raw rgba/hsla outside token or exception',
    regex: /\b(?:rgba?|hsla?)\(/g,
  },
  {
    name: 'inline hardcoded visual color',
    regex: /\b(?:color|background|backgroundColor|border|borderColor)\s*:\s*['"`][^'"`]*(?:#[0-9a-fA-F]{3,8}|rgba?\(|\b(?:white|black)\b)/g,
  },
]

const allowedPathFragments = [
  'src/image/',
  'src/styles/global.css',
  'src/components/common/ui/',
  'src/pages/HomePage/HomePage.css',
  'src/pages/LoginPage/LoginPage.css',
  'src/pages/dashboard/HomeHarnessAgent/components/openDesignShowcaseRenderer.ts',
  'src/pages/dashboard/HomeHarnessAgent/index.test.tsx',
  '.test.',
  'src/pages/dashboard/CanvasPage/brushRasterization.ts',
  'src/pages/dashboard/CanvasPage/canvasBrush.test.ts',
  'src/pages/dashboard/CanvasPage/components/CanvasSceneLayer.tsx',
  'src/pages/dashboard/CanvasPage/hooks/useCanvasController.media.ts',
  'src/pages/dashboard/CanvasPage/hooks/useCanvasController.tsx',
  'src/pages/dashboard/CanvasPage/hooks/useCanvasController.arrangement.ts',
  'src/pages/dashboard/CanvasPage/hooks/useCanvasAgentUpdates.ts',
  'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceCanvasArea.tsx',
  'src/pages/dashboard/HomeHarnessAgent/components/homeDesignSystemPreviewUtils.tsx',
]

const allowedInlineFragments = [
  // Govern app chrome with --app-* tokens. The exceptions below are not app
  // chrome: they render user content, paint/color-picker math, canvas overlays,
  // generated design previews, or test fixtures for those surfaces.
  //
  // Real color picker / paint controls render the user's chosen hue, alpha,
  // checkerboard, brush color, or palette value rather than application chrome.
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: "background: `rgb(${huePreview.r}, ${huePreview.g}, ${huePreview.b})`,",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: 'return `rgba(${Math.round(color.r)}, ${Math.round(color.g)}, ${Math.round(color.b)}, ${clamp(color.a, 0, 1)})`',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: "boxShadow: '0 2px 8px rgba(0,0,0,0.24)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: "background: 'linear-gradient(90deg, #ffffff 0%, rgba(255,255,255,0) 100%)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: "background: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, #000000 100%)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: "backgroundColor: colorToCss({ ...swatchColor, a: 1 })",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: "background: colorToCss({ ...visibleColor, a: 1 })",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: 'background: getCheckerboardBackground(10)',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: 'background: `linear-gradient(90deg, rgba(${visibleColor.r}, ${visibleColor.g}, ${visibleColor.b}, 0) 0%, ${alphaPreview} 100%)`',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolbar.tsx',
    text: "background: 'linear-gradient(90deg, #ff0000 0%, #ffff00 16%, #00ff00 33%, #00ffff 50%, #0000ff 66%, #ff00ff 83%, #ff0000 100%)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolPanel.tsx',
    text: 'backgroundColor: brushColor',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceMultiSelectToolbar.tsx',
    text: 'backgroundColor: color',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: "background: `rgb(${huePreview.r}, ${huePreview.g}, ${huePreview.b})`,",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: 'return `rgba(${Math.round(color.r)}, ${Math.round(color.g)}, ${Math.round(color.b)}, ${clamp(color.a, 0, 1)})`',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: "boxShadow: '0 2px 8px rgba(0,0,0,0.24)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: "background: 'linear-gradient(90deg, #ffffff 0%, rgba(255,255,255,0) 100%)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: "background: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, #000000 100%)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: 'background: `linear-gradient(90deg, rgba(${visibleColor.r}, ${visibleColor.g}, ${visibleColor.b}, 0) 0%, ${alphaPreview} 100%)`',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: 'background: colorToCss({ ...visibleColor, a: 1 })',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: 'background: colorToCss({ ...swatchColor, a: 1 })',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasTextToolbar.tsx',
    text: 'background: getCheckerboardBackground(10)',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceMediaRenderItem.tsx',
    text: "backgroundColor: 'rgba(255,255,255,0.65)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceMediaRenderItem.tsx',
    text: "boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.28)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/ImageEraseOverlay.tsx',
    text: "border: '1px dashed rgba(255,255,255,0.95)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/ImageEraseOverlay.tsx',
    text: "background: 'rgba(255,255,255,0.2)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/ImageEraseOverlay.tsx',
    text: 'rgba(255,255,255,',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/ImageEraseOverlay.tsx',
    text: 'background: `linear-gradient(to right, #8c8c8c ${brushProgress}%, #fff ${brushProgress}%)`',
  },
  // Test fixtures assert rendered content/selection appearances instead of app chrome.
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasBrushToolPanel.test.tsx',
    text: "color: '#111111'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasPerfHarnessPage.tsx',
    text: "border: '2px solid rgb(59, 130, 246)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceGroupLayer.test.tsx',
    text: 'border: `${borderWidth}px solid rgb(59, 130, 246)`',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceGroupLayer.test.tsx',
    text: "backgroundColor: '#fff'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceItemLayer.test.tsx',
    text: "border: '2px solid rgb(59, 130, 246)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceItemLayer.test.tsx',
    text: 'border: `${borderWidth}px solid rgb(59, 130, 246)`',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceItemLayer.test.tsx',
    text: "backgroundColor: '#fff'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceMultiSelectToolbar.test.tsx',
    text: "border: '1px solid #1677ff'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceTextRenderItem.test.tsx',
    text: 'border: `${borderWidth}px solid rgb(59, 130, 246)`',
  },
  {
    file: 'src/pages/dashboard/CanvasPage/components/CanvasWorkspaceTextRenderItem.test.tsx',
    text: "backgroundColor: '#fff'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/InteractionCard.test.tsx',
    text: "border: '1px solid rgba(15,23,42,0.1)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/InteractionCard.test.tsx',
    text: "border: '1px solid rgba(15,23,42,0.08)'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/MessageList.blocks.test.tsx',
    text: "border: '1px solid #ddd'",
  },
  {
    file: 'src/pages/dashboard/CanvasPage/MessageList.blocks.test.tsx',
    text: "border: '1px solid #eee'",
  },
  {
    file: 'src/pages/dashboard/HomeHarnessAgent/components/HomeChatMarkdown.test.tsx',
    text: "border: '1px solid #d4d4d8'",
  },
  {
    file: 'src/pages/dashboard/HomeHarnessAgent/components/HomeChatMarkdown.test.tsx',
    text: "border: '1px solid #e4e4e7'",
  },
  {
    file: 'src/store/canvasAgentStore.test.ts',
    text: "color: '#1677ff'",
  },
  {
    file: 'src/pages/dashboard/HomeHarnessAgent/components/HomeHarnessInteractionForm.tsx',
    text: 'style={{ backgroundColor: color }}',
  },
]

const extensions = new Set(['.ts', '.tsx', '.css'])
const strict = process.argv.includes('--strict')

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    if (entry.name === 'node_modules' || entry.name === 'dist') continue
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      files.push(...await walk(fullPath))
    } else if (extensions.has(path.extname(entry.name))) {
      files.push(fullPath)
    }
  }
  return files
}

function normalize(file) {
  return path.relative(root, file).replaceAll(path.sep, '/')
}

function isAllowed(relativePath) {
  return allowedPathFragments.some((fragment) => relativePath.includes(fragment))
}

function isAllowedFinding(relativePath, line) {
  if (isAllowedOpacityLine(line)) {
    return true
  }
  return allowedInlineFragments.some((entry) => (
    relativePath === entry.file && line.includes(entry.text)
  ))
}

function isAllowedOpacityLine(line) {
  const opacityUtility = /\bopacity-(?:[1-9][0-9]?|100)\b|\bopacity\s*:\s*(?:0?\.\d+|[01])\b/
  if (!opacityUtility.test(line)) {
    return false
  }

  return (
    line.includes('disabled:opacity-')
    || line.includes('data-[disabled]:opacity-')
    || line.includes('cursor-not-allowed')
    || line.includes('opacity-0')
    || line.includes('opacity-100')
    || line.includes('opacity: 0')
    || line.includes('opacity: 1')
    || line.includes('hover:opacity-')
    || line.includes('group-hover:opacity-')
    || line.includes('focus-visible:opacity-')
    || line.includes('transition-opacity')
    || line.includes('animate={{ opacity')
    || line.includes('initial={{ opacity')
    || line.includes('exit={{ opacity')
    || line.includes('from { opacity')
    || line.includes('from { transform')
    || line.includes('to { opacity')
    || line.includes('to { transform')
    || line.includes('0%, 100% { opacity')
    || line.includes('50% { opacity')
    || line.includes('isSelected ?')
    || line.includes('isSubmitted')
    || line.includes('isSubmitting')
    || line.includes('disabled ?')
  )
}

const files = await walk(srcDir)
const findings = []

for (const file of files) {
  const relativePath = normalize(file)
  if (isAllowed(relativePath)) continue
  const content = await readFile(file, 'utf8')
  const lines = content.split(/\r?\n/)
  lines.forEach((line, index) => {
    if (isAllowedFinding(relativePath, line)) return
    for (const pattern of patterns) {
      pattern.regex.lastIndex = 0
      if (pattern.regex.test(line)) {
        findings.push({
          file: relativePath,
          line: index + 1,
          pattern: pattern.name,
          text: line.trim().slice(0, 180),
        })
      }
    }
  })
}

if (findings.length) {
  console.log(`Hardcoded style scan found ${findings.length} finding(s).`)
  findings.slice(0, 120).forEach((finding) => {
    console.log(`${finding.file}:${finding.line} [${finding.pattern}] ${finding.text}`)
  })
  if (findings.length > 120) {
    console.log(`...and ${findings.length - 120} more.`)
  }
  if (strict) {
    process.exitCode = 1
  }
} else {
  console.log('Hardcoded style scan passed.')
}
