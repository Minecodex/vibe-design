import { memo, useMemo, useState } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import { useTranslation } from 'react-i18next'
import remarkGfm from 'remark-gfm'

import { ImagePreviewDialog } from '@/components/common/ZoomableImageViewer'

import { GenerationArtifactReferenceChip } from './GenerationArtifactReferenceChip'
import { HomeChatFileReferenceChip } from './HomeChatFileReferenceChip'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'
import {
  createGenerationArtifactReferenceRemarkPlugin,
  decodeGenerationArtifactReferenceHref,
  GENERATION_ARTIFACT_REFERENCE_SCHEME,
  normalizeGenerationArtifactRef,
} from './generationArtifactMarkdownReferences'
import {
  createWorkspaceFileReferenceResolver,
  HOME_CHAT_WORKSPACE_FILE_REFERENCE_SCHEME,
} from './homeChatFinalAnswerFileReferences'
import { useHarnessMediaSource } from './useHarnessMediaSource'
import type { SessionFileItem } from '../homeHarnessPageUtils'

interface HomeChatMarkdownProps {
  content: string
  isDark: boolean
  className?: string
  conversationId?: string | number | null
  workspaceFiles?: SessionFileItem[]
  enableWorkspaceFileReferences?: boolean
  enableArtifactReferences?: boolean
  onOpenWorkspaceFile?: (file: SessionFileItem) => void
}

interface PreviewImageState {
  src: string
  alt: string
}

// Memoized so finalized assistant markdown is not re-parsed by ReactMarkdown on every
// streaming delta / parent re-render. Content is stable for completed messages.
export const HomeChatMarkdown = memo(HomeChatMarkdownImpl)

function HomeChatMarkdownImpl({
  content,
  isDark,
  className,
  conversationId,
  workspaceFiles,
  enableWorkspaceFileReferences = false,
  enableArtifactReferences = false,
  onOpenWorkspaceFile,
}: HomeChatMarkdownProps) {
  const { t } = useTranslation()
  const [previewImage, setPreviewImage] = useState<PreviewImageState | null>(null)
  const fileReferenceResolver = useMemo(
    () => enableWorkspaceFileReferences
      ? createWorkspaceFileReferenceResolver(workspaceFiles)
      : null,
    [enableWorkspaceFileReferences, workspaceFiles],
  )
  const artifactReferenceRemarkPlugin = useMemo(
    () => enableArtifactReferences ? createGenerationArtifactReferenceRemarkPlugin() : null,
    [enableArtifactReferences],
  )
  const remarkPlugins = useMemo(
    () => [
      remarkGfm,
      ...(fileReferenceResolver ? [fileReferenceResolver.remarkPlugin] : []),
      ...(artifactReferenceRemarkPlugin ? [artifactReferenceRemarkPlugin] : []),
    ],
    [artifactReferenceRemarkPlugin, fileReferenceResolver],
  )

  const openPreview = (displaySrc: string, alt: string) => {
    setPreviewImage({ src: displaySrc, alt })
  }

  const renderFileReferenceChip = (file: SessionFileItem) => (
    <HomeChatFileReferenceChip
      file={file}
      conversationId={conversationId}
      isDark={isDark}
      t={t}
      onOpen={(nextFile) => onOpenWorkspaceFile?.(nextFile)}
    />
  )

  const renderArtifactReferenceChip = (artifactRef: string) => (
    <GenerationArtifactReferenceChip
      artifactRef={artifactRef}
      conversationId={conversationId}
      isDark={isDark}
      onPreviewImage={(src, alt) => openPreview(src, alt)}
    />
  )

  return (
    <>
      <div
        className={className}
        style={{
          fontSize: 15,
          lineHeight: 1.7,
          color: 'var(--app-foreground-muted)',
          whiteSpace: 'normal',
          wordBreak: 'break-word',
        }}
      >
        <ReactMarkdown
          remarkPlugins={remarkPlugins}
          urlTransform={(url) => (
            String(url || '').startsWith(HOME_CHAT_WORKSPACE_FILE_REFERENCE_SCHEME)
              || String(url || '').startsWith(GENERATION_ARTIFACT_REFERENCE_SCHEME)
              || normalizeGenerationArtifactRef(String(url || ''))
              ? url
              : defaultUrlTransform(url)
          )}
          components={{
            h1: ({ children }) => <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 12px', color: 'var(--app-foreground)' }}>{children}</h1>,
            h2: ({ children }) => <h2 style={{ fontSize: 20, fontWeight: 700, margin: '0 0 10px', color: 'var(--app-foreground)' }}>{children}</h2>,
            h3: ({ children }) => <h3 style={{ fontSize: 17, fontWeight: 600, margin: '0 0 8px', color: 'var(--app-foreground)' }}>{children}</h3>,
            p: ({ children }) => <p style={{ margin: '0 0 10px' }}>{children}</p>,
            ul: ({ children }) => <ul style={{ margin: '0 0 10px', paddingLeft: 22 }}>{children}</ul>,
            ol: ({ children }) => <ol style={{ margin: '0 0 10px', paddingLeft: 22 }}>{children}</ol>,
            li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
            strong: ({ children }) => <strong style={{ fontWeight: 700, color: 'var(--app-foreground)' }}>{children}</strong>,
            blockquote: ({ children }) => (
              <blockquote
                style={{
                  margin: '0 0 10px',
                  paddingLeft: 12,
                  borderLeft: '3px solid var(--app-border-strong)',
                  color: 'var(--app-foreground-muted)',
                }}
              >
                {children}
              </blockquote>
            ),
            code: ({ className: codeClassName, children, ...props }) => {
              const isInline = !codeClassName
              if (isInline) {
                const inlineCodeText = String(children || '').trim()
                const referencedArtifact = enableArtifactReferences ? normalizeGenerationArtifactRef(inlineCodeText) : null
                if (referencedArtifact) {
                  return renderArtifactReferenceChip(referencedArtifact)
                }

                const referencedFile = fileReferenceResolver?.getFileForInlineCode(inlineCodeText)
                if (referencedFile && onOpenWorkspaceFile) {
                  return renderFileReferenceChip(referencedFile)
                }

                return (
                  <code
                    style={{
                      padding: '1px 5px',
                      borderRadius: 6,
                      backgroundColor: 'var(--app-control)',
                      fontSize: 13,
                      fontFamily: 'Menlo, Monaco, Consolas, monospace',
                      color: 'var(--app-primary)',
                    }}
                    {...props}
                  >
                    {children}
                  </code>
                )
              }

              return (
                <code
                  style={{
                    display: 'block',
                    padding: 12,
                    borderRadius: 10,
                    backgroundColor: 'var(--app-surface-muted)',
                    border: '1px solid var(--app-border)',
                    fontSize: 13,
                    fontFamily: 'Menlo, Monaco, Consolas, monospace',
                    overflowX: 'auto',
                    marginBottom: 10,
                    whiteSpace: 'pre',
                  }}
                  className={codeClassName}
                  {...props}
                >
                  {children}
                </code>
              )
            },
            pre: ({ children }) => <>{children}</>,
            table: ({ children }) => (
              <div style={{ overflowX: 'auto', margin: '0 0 12px' }}>
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    border: '1px solid var(--app-border)',
                    fontSize: 14,
                  }}
                >
                  {children}
                </table>
              </div>
            ),
            th: ({ children }) => (
              <th
                style={{
                  padding: '8px 10px',
                  border: '1px solid var(--app-border)',
                  backgroundColor: 'var(--app-surface-muted)',
                  textAlign: 'left',
                  fontWeight: 600,
                  color: 'var(--app-foreground)',
                }}
              >
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td
                style={{
                  padding: '8px 10px',
                  border: '1px solid var(--app-border)',
                  color: 'var(--app-foreground-muted)',
                }}
              >
                {children}
              </td>
            ),
            a: ({ href, children }) => {
              const referencedArtifact = enableArtifactReferences ? decodeGenerationArtifactReferenceHref(href) : null
              if (referencedArtifact) {
                return renderArtifactReferenceChip(referencedArtifact)
              }

              const referencedFile = fileReferenceResolver?.getFileForHref(href)
              if (referencedFile && onOpenWorkspaceFile) {
                return renderFileReferenceChip(referencedFile)
              }
              return (
                <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--app-primary)', textDecoration: 'none' }}>
                  {children}
                </a>
              )
            },
            img: ({ src, alt }) => (
              <MarkdownImage
                src={src || ''}
                alt={alt || 'Markdown image'}
                conversationId={conversationId}
                onPreview={(displaySrc) => openPreview(displaySrc, alt || 'Markdown image')}
              />
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>

      <ImagePreviewDialog
        open={!!previewImage}
        onOpenChange={(open) => !open && setPreviewImage(null)}
        src={previewImage?.src || null}
        alt={previewImage?.alt || 'Markdown image preview'}
        title={previewImage?.alt || 'Markdown image preview'}
        imageClassName="rounded-2xl"
        downloadUrl={previewImage?.src || null}
      />
    </>
  )
}

interface MarkdownImageProps {
  src: string
  alt: string
  conversationId?: string | number | null
  onPreview: (displaySrc: string) => void
}

// Generated assets may not be on disk yet when the AI's answer renders; the
// preview route returns 503 until they land. Retry with exponential backoff
// (2s to 30s cap) for up to roughly 10 minutes while showing a placeholder.
const MAX_GENERATED_RETRIES = 12

function isGeneratedAssetPath(path: string): boolean {
  return /references\/generated\//.test(path)
}

function MarkdownImage({ src, alt, conversationId, onPreview }: MarkdownImageProps) {
  const { t } = useTranslation()
  const normalizedSrc = resolveMarkdownImagePath(src)
  const isGenerated = isGeneratedAssetPath(normalizedSrc)
  const [retryCount, setRetryCount] = useState(0)
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  const displayUrl = useHarnessMediaSource(conversationId, normalizedSrc, {
    preferPreviewUrl: true,
    reloadToken: retryCount,
    variant: 'thumb-1024',
  }) || ''

  const handleError = () => {
    if (!displayUrl) {
      return
    }
    if (!isGenerated || retryCount >= MAX_GENERATED_RETRIES) {
      setFailed(true)
      return
    }
    const delay = Math.min(2000 * 2 ** retryCount, 30000)
    window.setTimeout(() => setRetryCount((count) => count + 1), delay)
  }

  const showPlaceholder = isGenerated && !loaded && !failed

  return (
    <span style={{ display: 'block', margin: '12px 0' }}>
      {showPlaceholder && (
        <span
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: 120,
            padding: '24px 16px',
            borderRadius: 16,
            border: '1px dashed var(--app-border-strong)',
            color: 'var(--app-foreground-muted)',
            fontSize: 13,
            background: 'var(--app-surface-muted)',
          }}
        >
          {alt
            ? t('homeHarness.media.generatingImageWithAlt', 'Generating: {{alt}}...', { alt })
            : t('homeHarness.media.generatingImage', 'Generating image...')}
        </span>
      )}
      <AgentLazyMedia
        key={retryCount}
        src={displayUrl}
        alt={alt}
        aspectRatio={16 / 9}
        as="span"
        className="rounded-2xl"
        mediaStyle={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          display: showPlaceholder ? 'none' : 'block',
        }}
        onImageLoad={() => setLoaded(true)}
        onImageError={handleError}
        style={{
          maxWidth: '100%',
          minHeight: 120,
          background: 'var(--app-surface-muted)',
          cursor: displayUrl ? 'zoom-in' : 'default',
        }}
        onClick={() => displayUrl && onPreview(displayUrl)}
      />
    </span>
  )
}

function resolveMarkdownImagePath(src: string) {
  return String(src || '').trim().replace(/\\/g, '/')
}
