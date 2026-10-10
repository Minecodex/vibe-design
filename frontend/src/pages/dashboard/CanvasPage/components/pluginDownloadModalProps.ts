export interface PluginDownloadModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  t?: (key: string, fallback?: string) => string
}
