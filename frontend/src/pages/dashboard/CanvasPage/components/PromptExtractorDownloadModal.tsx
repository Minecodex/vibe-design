import { Download, Languages, MousePointerClick } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { getApiOrigin } from '@/config/runtimeConfig'

const PROMPT_EXTRACTOR_NAME = '提取插件'
const PROMPT_EXTRACTOR_ZIP_URL = `/downloads/prompt-extractor/latest/${encodeURIComponent(PROMPT_EXTRACTOR_NAME)}.zip`

function getServiceAddress() {
  if (typeof window === 'undefined') {
    return ''
  }

  return getApiOrigin()
}

export function PromptExtractorDownloadModal(props: any) {
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
            {t('canvas.prompt_extractor.modal_title', '安装提取插件')}
          </DialogTitle>
          <DialogDescription className="text-sm leading-6">
            {t(
              'canvas.prompt_extractor.modal_description',
              '下载 ZIP 后解压，在 Google Chrome 中开启开发者模式并加载已解压的扩展程序。首次打开插件后登录账户，即可在网页图片上右键提取文生图提示词。',
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="rounded-2xl border border-border/70 bg-muted/40 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild className="gap-2">
                <a href={PROMPT_EXTRACTOR_ZIP_URL} download={`${PROMPT_EXTRACTOR_NAME}.zip`}>
                  <Download className="size-4" />
                  {t('canvas.prompt_extractor.download_zip', '下载 ZIP')}
                </a>
              </Button>
              <p className="text-sm text-muted-foreground">
                {t(
                  'canvas.prompt_extractor.download_hint',
                  '下载后请先解压 ZIP，再去 Chrome 扩展管理页导入。',
                )}
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-border/70 bg-background p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <MousePointerClick className="size-4 text-primary" />
              <span>{t('canvas.prompt_extractor.install_title', '安装步骤')}</span>
            </div>
            <ol className="grid gap-3 text-sm leading-6 text-foreground/90">
              <li>{t('canvas.prompt_extractor.install_step_download', '1. 下载并解压提取插件 ZIP。')}</li>
              <li>{t('canvas.prompt_extractor.install_step_extensions', '2. 打开 chrome://extensions')}</li>
              <li>{t('canvas.prompt_extractor.install_step_dev_mode', '3. 在右上角开启“开发者模式”。')}</li>
              <li>{t('canvas.prompt_extractor.install_step_load', '4. 点击“加载已解压的扩展程序”。')}</li>
              <li>{t('canvas.prompt_extractor.install_step_select', '5. 选择刚刚解压出来的插件目录并确认。')}</li>
              <li>{t('canvas.prompt_extractor.install_step_login', '6. 安装后打开插件，检查服务地址并登录账户密码。')}</li>
            </ol>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-border/70 bg-background p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                <Languages className="size-4 text-primary" />
                <span>{t('canvas.prompt_extractor.usage_title', '使用方式')}</span>
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                {t(
                  'canvas.prompt_extractor.usage_body',
                  '登录后，在网页图片上右键即可看到“提取提示词”。结果弹窗支持中文与 English 切换，切换语言后会重新请求服务端生成对应语言版本。',
                )}
              </p>
            </div>

            <div className="rounded-2xl border border-border/70 bg-background p-4">
              <div className="mb-2 text-sm font-medium">
                {t('canvas.prompt_extractor.service_title', '服务地址')}
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                {t(
                  'canvas.prompt_extractor.service_body',
                  '服务地址来自 APP_API_BASE_URL 配置。若插件内未自动带出，可填写下面这个后端地址：',
                )}
              </p>
              <code className="mt-3 block rounded-xl bg-muted px-3 py-2 text-sm">
                {serviceAddress || t('canvas.prompt_extractor.service_empty', '请填写当前站点域名')}
              </code>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
