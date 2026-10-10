import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Terminal, ChevronDown, ChevronRight, Copy, Check } from 'lucide-react'

interface CodeExecutionBlockProps {
    toolName: string
    callId: string
    args?: Record<string, unknown>
    output?: string
    isError?: boolean
    elapsedMs?: number
    isDark: boolean
}

export function CodeExecutionBlock({
    toolName,
    callId: _callId,
    args,
    output,
    isError,
    elapsedMs,
    isDark,
}: CodeExecutionBlockProps) {
    void _callId
    const [expanded, setExpanded] = useState(false)
    const [copied, setCopied] = useState(false)

    const command = typeof args?.command === 'string' ? args.command : ''
    const displayName = toolName === 'bash' ? (command?.split('\n')[0] || 'bash') : toolName
    const isRunning = output === undefined
    const elapsedLabel = typeof elapsedMs === 'number' && Number.isFinite(elapsedMs)
        ? `${elapsedMs}ms`
        : null

    const handleCopy = () => {
        const text = output || command || ''
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
    }

    return (
        <div className={cn(
            'app-card overflow-hidden rounded-xl my-2',
        )}>
            {/* Header */}
            <button
                onClick={() => setExpanded(!expanded)}
                className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-[var(--app-control-hover)]',
                )}
            >
                <Terminal className={cn('w-3.5 h-3.5 shrink-0', isError ? 'text-red-500' : 'text-emerald-500')} />
                {expanded
                    ? <ChevronDown className="w-3.5 h-3.5 shrink-0 text-zinc-500" />
                    : <ChevronRight className="w-3.5 h-3.5 shrink-0 text-zinc-500" />
                }
                <span className={cn(
                    'font-mono text-xs truncate flex-1 text-left',
                    isDark ? 'text-zinc-300' : 'text-zinc-700',
                )}>
                    {displayName}
                </span>
                {isRunning ? (
                    <span className="text-xs text-blue-500 animate-pulse">running...</span>
                ) : (
                    <span className={cn(
                        'text-xs',
                        isError ? 'text-red-500' : 'text-zinc-500',
                    )}>
                        {isError ? 'error' : (elapsedLabel || 'done')}
                    </span>
                )}
            </button>

            {/* Expandable content */}
            {expanded && (
                <div className={cn(
                    'app-divider border-t px-3 py-2 relative',
                )}>
                    <button
                        onClick={handleCopy}
                        className={cn(
                            'app-muted absolute top-2 right-2 p-1 rounded transition-colors hover:bg-[var(--app-control-hover)]',
                        )}
                    >
                        {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>

                    {/* Command */}
                    {toolName === 'bash' && command && (
                        <div className="mb-2">
                            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">command</div>
                            <pre className={cn(
                                'text-xs font-mono whitespace-pre-wrap break-all max-h-40 overflow-y-auto',
                                isDark ? 'text-zinc-300' : 'text-zinc-700',
                            )}>
                                {command}
                            </pre>
                        </div>
                    )}

                    {/* Output */}
                    {output && (
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">output</div>
                            <pre className={cn(
                                'text-xs font-mono whitespace-pre-wrap break-all max-h-60 overflow-y-auto',
                                isError ? 'text-red-400' : (isDark ? 'text-zinc-400' : 'text-zinc-600'),
                            )}>
                                {output}
                            </pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
