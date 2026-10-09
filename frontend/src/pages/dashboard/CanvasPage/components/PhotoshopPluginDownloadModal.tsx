import type { PluginDownloadModalProps } from './pluginDownloadModalProps'
import { Download, Layers, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { getApiOrigin } from '@/config/runtimeConfig'

const PHOTOSHOP_PLUGIN_PACKAGE_FILE = 'canvas-photoshop-plugin.zip'
const PHOTOSHOP_PLUGIN_ZIP_URL = `/downloads/photoshop-uxp/latest/${PHOTOSHOP_PLUGIN_PACKAGE_FILE}`

function getServiceAddress() {
  if (typeof window === 'undefined') {
    return ''
  }

  return getApiOrigin()
}

export function PhotoshopPluginDownloadModal(props: PluginDownloadModalProps) {
  const {
    open,
    onOpenChange,
    t = (_key: string, fallback?: string) => fallback || '',
  } = props

  const serviceAddress = getServiceAddress()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        overlayClassName="z-[2147483647]"
        className="z-[2147483647] max-w-[92vw] sm:max-w-[720px]"
      >
        <DialogHeader className="gap-3">
          <DialogTitle className="text-xl">
            {t('canvas.photoshop_plugin.modal_title', '安装 Photoshop 插件')}
          </DialogTitle>
          <DialogDescription className="text-sm leading-6">
            {t(
              'canvas.photoshop_plugin.modal_description',
              '下载 Photoshop UXP 插件压缩包后，解压并通过 UXP Developer Tool 选择 manifest.json 导入。安装完成后打开插件并登录，即可接收画布中的 PS 编辑任务。',
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="rounded-2xl border border-border/70 bg-muted/40 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild className="gap-2">
                <a href={PHOTOSHOP_PLUGIN_ZIP_URL} download={PHOTOSHOP_PLUGIN_PACKAGE_FILE}>
                  <Download className="size-4" />
                  {t('canvas.photoshop_plugin.download_zip', '下载 ZIP')}
                </a>
              </Button>
              <p className="text-sm text-muted-foreground">
                {t(
                  'canvas.photoshop_plugin.download_hint',
                  '下载后先解压，在 UXP Developer Tool 中点击 Add Plugin 并选择解压目录里的 manifest.json。',
                )}
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-border/70 bg-background p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Layers className="size-4 text-primary" />
              <span>{t('canvas.photoshop_plugin.install_title', '安装步骤')}</span>
            </div>
            <ol className="grid gap-3 text-sm leading-6 text-foreground/90">
              <li>{t('canvas.photoshop_plugin.install_step_download', '1. 下载 Photoshop 插件压缩包（.zip）并解压。')}</li>
              <li>{t('canvas.photoshop_plugin.install_step_dev_mode', '2. 打开 Photoshop，进入“增效工具”，开启开发者模式。')}</li>
              <li>{t('canvas.photoshop_plugin.install_step_uxp_tool', '3. 打开 UXP Developer Tool，点击 Add Plugin，选择解压目录中的 manifest.json。')}</li>
              <li>{t('canvas.photoshop_plugin.install_step_load', '4. 在 UXP Developer Tool 中点击 Load。')}</li>
              <li>{t('canvas.photoshop_plugin.install_step_open', '5. 回到 Photoshop，从“增效工具”面板中打开 Canvas Photoshop Plugin。')}</li>
              <li>{t('canvas.photoshop_plugin.install_step_login', '6. 插件会带出后端服务地址，也可按实际环境修改后登录。')}</li>
            </ol>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-border/70 bg-background p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                <Sparkles className="size-4 text-primary" />
                <span>{t('canvas.photoshop_plugin.usage_title', '使用方式')}</span>
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                {t(
                  'canvas.photoshop_plugin.usage_body',
                  '在画布右键图片选择“PS 编辑”后，插件会监听到新的待处理任务，并弹出确认框询问是否导入到 Photoshop。',
                )}
              </p>
            </div>

            <div className="rounded-2xl border border-border/70 bg-background p-4">
              <div className="mb-2 text-sm font-medium">
                {t('canvas.photoshop_plugin.service_title', '服务地址')}
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                {t(
                  'canvas.photoshop_plugin.service_body',
                  '服务地址来自 APP_API_BASE_URL 配置。若开发环境下需要手动检查，可确认以下后端地址是否正确：',
                )}
              </p>
              <code className="mt-3 block rounded-xl bg-muted px-3 py-2 text-sm">
                {serviceAddress || t('canvas.photoshop_plugin.service_empty', '请填写当前站点域名')}
              </code>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
