import { ImagePreviewDialog } from '@/components/common/ZoomableImageViewer'

type ImagePreviewOverlayProps = {
  previewImageUrl: string | null
  setPreviewImageUrl: (url: string | null) => void
}

export function ImagePreviewOverlay({
  previewImageUrl,
  setPreviewImageUrl,
}: ImagePreviewOverlayProps) {
  return (
    <ImagePreviewDialog
      open={!!previewImageUrl}
      onOpenChange={(open) => !open && setPreviewImageUrl(null)}
      src={previewImageUrl}
      alt="Preview"
      title="Preview"
      imageClassName="rounded-xl"
      downloadUrl={previewImageUrl}
    />
  )
}
