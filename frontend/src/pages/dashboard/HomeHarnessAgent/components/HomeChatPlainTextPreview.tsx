interface HomeChatPlainTextPreviewProps {
  content: string
  isDark: boolean
  className?: string
}

export function HomeChatPlainTextPreview({
  content,
  className,
}: HomeChatPlainTextPreviewProps) {
  return (
    <pre
      className={className}
      style={{
        margin: 0,
        padding: 0,
        fontSize: 13,
        lineHeight: 1.75,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        tabSize: 2,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
        color: 'var(--app-foreground)',
      }}
    >
      {content}
    </pre>
  )
}
