import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

describe('Chinese fallback copy', () => {
  it('keeps project and canvas fallback labels readable', () => {
    const currentDir = dirname(fileURLToPath(import.meta.url))
    const projectDetailsViewSource = readFileSync(
      resolve(currentDir, '../components/project/ProjectDetailsView.tsx'),
      'utf8',
    )
    const assetLibraryImportSource = readFileSync(
      resolve(currentDir, '../pages/dashboard/CanvasPage/hooks/useAssetLibraryImport.ts'),
      'utf8',
    )
    const canvasWorkspaceFloatingPanelsSource = readFileSync(
      resolve(currentDir, '../pages/dashboard/CanvasPage/components/CanvasWorkspaceFloatingPanels.tsx'),
      'utf8',
    )
    const canvasWorkspaceMediaSource = readFileSync(
      resolve(currentDir, '../pages/dashboard/CanvasPage/components/CanvasWorkspaceMediaRenderItem.tsx'),
      'utf8',
    )
    const chatSidebarSource = readFileSync(
      resolve(currentDir, '../pages/dashboard/CanvasPage/hooks/useChatSidebar.ts'),
      'utf8',
    )

    expect(projectDetailsViewSource).toContain("defaultValue: '我的收藏'")
    expect(projectDetailsViewSource).not.toContain('閹存垹娈戦弨鎯版')
    expect(projectDetailsViewSource).not.toContain('闁瑰瓨鍨瑰▓鎴﹀绩閹増顥?')

    expect(assetLibraryImportSource).toContain("t('canvas.tools.import_success', '导入成功')")
    expect(assetLibraryImportSource).not.toContain('鐎电厧鍙嗛幋鎰')
    expect(assetLibraryImportSource).not.toContain('閻庣數鍘ч崣鍡涘箣閹邦剙顫?')

    expect(canvasWorkspaceFloatingPanelsSource).toContain("t('canvas.chat.tool_tips.gen_video', '生成视频')")
    expect(canvasWorkspaceFloatingPanelsSource).toContain("t('canvas.chat.tool_tips.hd_upscale', '高清')")
    expect(canvasWorkspaceFloatingPanelsSource).toContain("t('canvas.chat.tool_tips.cutout', '抠图')")
    expect(canvasWorkspaceFloatingPanelsSource).toContain("t('canvas.chat.tool_tips.erase', '消除笔')")
    expect(canvasWorkspaceFloatingPanelsSource).toContain("t('canvas.chat.tool_tips.redraw_text', '文字重绘')")
    expect(canvasWorkspaceFloatingPanelsSource).toContain("t('canvas.toolbar.spatial_angle', '空间角度')")
    expect(canvasWorkspaceFloatingPanelsSource).toContain("t('canvas.toolbar.crop', '裁剪')")
    expect(canvasWorkspaceFloatingPanelsSource).toContain("t('canvas.toolbar.image_info', '图片信息')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.crop.presets_label', '预设')")
    expect(canvasWorkspaceMediaSource).toContain("t('processing', '处理中...')")
    expect(canvasWorkspaceMediaSource).toContain("t('done', '完成')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.generator.generate_now', '立即生成')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.generator.model_label', '生成模型')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.generator.resolution_label', '精度设置')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.generator.duration_label', '时长设置')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.generator.resolution_prefix', '精度: ')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.generator.duration_prefix', '时长: ')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.generator.ratio_label', '画布比例')")
    expect(canvasWorkspaceMediaSource).toContain("t('canvas.generator.ratio_prefix', '比例: ')")
    expect(canvasWorkspaceFloatingPanelsSource).not.toContain('\ufffd')
    expect(canvasWorkspaceMediaSource).not.toContain('\ufffd')
    expect(canvasWorkspaceFloatingPanelsSource).not.toContain('閻㈢喐鍨氱憴鍡涱暥')
    expect(canvasWorkspaceMediaSource).not.toContain('妤傛ɑ绔?')
    expect(canvasWorkspaceMediaSource).not.toContain('閹剁姴娴?')
    expect(canvasWorkspaceMediaSource).not.toContain('閹匡箓娅?')
    expect(canvasWorkspaceMediaSource).not.toContain('閺傚洤鐡ч柌宥囩帛')
    expect(canvasWorkspaceMediaSource).not.toContain('缁屾椽妫跨憴鎺戝')
    expect(canvasWorkspaceMediaSource).not.toContain('閸ュ墽澧栨穱鈩冧紖')

    expect(chatSidebarSource).toContain("t('billing.insufficient', '余额不足，无法发起新会话')")
    expect(chatSidebarSource).not.toContain('缁夘垰鍨庢稉宥堝喕閿涘本妫ゅ▔鏇炲絺鐠ч攱鏌婃导姘崇樈')
  })
})
