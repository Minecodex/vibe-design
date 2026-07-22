import type { HomeChatOfficePresentationSnapshot } from './homeChatOfficeSnapshots'

interface HomeChatPptPreviewProps {
  snapshot?: HomeChatOfficePresentationSnapshot | null
}

export function HomeChatPptPreview({ snapshot }: HomeChatPptPreviewProps) {
  const slides = Array.isArray(snapshot?.slides) ? snapshot.slides : []

  return (
    <div
      data-testid="home-chat-office-presentation-preview"
      className="app-card-muted app-muted flex h-full min-h-0 flex-col gap-4 rounded-2xl border-dashed p-6 text-sm"
    >
      <div>
        Presentation preview is read-only for now.
      </div>
      {snapshot?.warning ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          {snapshot.warning}
        </div>
      ) : null}
      {slides.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2">
          {slides.map((slide, index) => (
            <div key={`${slide.title || 'slide'}-${index}`} className="app-card rounded-xl p-4">
              <div className="app-subtle text-xs uppercase tracking-[0.18em]">
                Slide {index + 1}
              </div>
              <div className="app-text mt-2 font-medium">
                {slide.title || 'Untitled slide'}
              </div>
              {slide.bullets?.length ? (
                <div className="app-muted mt-2 space-y-1 text-xs">
                  {slide.bullets.map((bullet, bulletIndex) => (
                    <div key={`${bullet}-${bulletIndex}`}>{bullet}</div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="app-card rounded-xl p-4 text-xs">
          Use Download to inspect the original presentation file.
        </div>
      )}
    </div>
  )
}
