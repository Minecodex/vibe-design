import { useTranslation } from 'react-i18next'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface DeleteAssetsConfirmDialogProps {
  count: number
  open: boolean
  onConfirm: () => void
  onOpenChange: (open: boolean) => void
  variant: 'batch' | 'single'
}

export function DeleteAssetsConfirmDialog({
  count,
  open,
  onConfirm,
  onOpenChange,
  variant,
}: DeleteAssetsConfirmDialogProps) {
  const { t } = useTranslation()
  const isSingleAsset = variant === 'single'

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        noDarken
        className="glass-modal-unified max-w-[420px] rounded-[28px] border-none p-7 shadow-2xl"
      >
        <AlertDialogHeader className="space-y-3">
          <AlertDialogTitle className="text-xl font-bold tracking-tight text-foreground">
            {isSingleAsset
              ? t('delete_asset_confirm_title', '确定要删除该素材吗？')
              : t('delete_assets_confirm_title', '确定要删除选中的 {{count}} 个素材吗？', { count })}
          </AlertDialogTitle>
          <AlertDialogDescription className="text-sm font-medium leading-relaxed text-muted-foreground">
            {isSingleAsset
              ? t('delete_asset_confirm_desc', '删除后将无法恢复。')
              : t('delete_assets_confirm_desc', '批量删除后将无法恢复。')}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="mt-6 gap-3 sm:justify-end">
          <AlertDialogCancel className="h-11 rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-transparent px-6 text-sm font-bold text-foreground transition-all hover:bg-[var(--app-control-hover)]">
            {t('common.cancel', '取消')}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="h-11 rounded-[var(--app-radius-sm)] border-none bg-[var(--app-danger)] px-6 text-sm font-bold text-white shadow-lg transition-all hover:bg-[var(--app-danger-hover)]"
          >
            {t('delete', '删除')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
