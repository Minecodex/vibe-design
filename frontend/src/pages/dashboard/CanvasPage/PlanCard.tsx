import { Loader2, CheckCircle2, XCircle, Circle, ListChecks } from 'lucide-react'
import type { PlanRead } from '@/api/endpoints/agent'

interface PlanCardProps {
    plan: PlanRead
    onApprove: (planId: number) => void
    onReject: (planId: number) => void
}

export function PlanCard({ plan, onApprove, onReject }: PlanCardProps) {
    const statusIcon = (status: string) => {
        switch (status) {
            case 'pending': return <Circle size={14} color="var(--app-foreground-subtle)" />
            case 'running': return <Loader2 size={14} color="var(--app-primary)" style={{ animation: 'spin 1s linear infinite' }} />
            case 'completed': return <CheckCircle2 size={14} color="var(--app-success)" />
            case 'failed': return <XCircle size={14} color="var(--app-danger)" />
            default: return <Circle size={14} color="var(--app-foreground-subtle)" />
        }
    }

    const showActions = plan.status === 'pending'
    const isExecuting = plan.status === 'executing'

    return (
        <div style={{
            margin: '8px 0',
            borderRadius: 16,
            border: '1px solid var(--app-border)',
            backgroundColor: 'var(--app-surface)',
            overflow: 'hidden',
        }}>
            {/* Header */}
            <div style={{
                padding: '12px 16px',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                borderBottom: '1px solid var(--app-border)',
            }}>
                <ListChecks size={16} color="var(--app-primary)" />
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--app-foreground)', flex: 1 }}>
                    {plan.summary || '执行计划'}
                </span>
                {isExecuting && <Loader2 size={14} color="var(--app-primary)" style={{ animation: 'spin 1s linear infinite' }} />}
            </div>

            {/* Steps */}
            <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {plan.steps.map((step: any) => (
                    <div key={step.step_number || step.id} style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        fontSize: 13,
                        color: 'var(--app-foreground-muted)',
                    }}>
                        {statusIcon(step.status)}
                        <span style={{
                            color: 'var(--app-foreground-subtle)',
                            minWidth: 20,
                        }}>
                            {step.step_number}.
                        </span>
                        <span style={{ flex: 1 }}>{step.description}</span>
                    </div>
                ))}
            </div>

            {/* Actions */}
            {showActions && (
                <div style={{
                    padding: '12px 16px',
                    borderTop: '1px solid var(--app-border)',
                    display: 'flex',
                    gap: 10,
                    justifyContent: 'flex-end',
                }}>
                    <button
                        onClick={() => onReject(plan.id)}
                        style={{
                            padding: '6px 16px',
                            borderRadius: 20,
                            border: '1px solid var(--app-border)',
                            backgroundColor: 'transparent',
                            color: 'var(--app-foreground-muted)',
                            fontSize: 13,
                            cursor: 'pointer',
                        }}
                    >
                        拒绝
                    </button>
                    <button
                        onClick={() => onApprove(plan.id)}
                        style={{
                            padding: '6px 16px',
                            borderRadius: 20,
                            border: 'none',
                            backgroundColor: 'var(--app-primary)',
                            color: 'var(--app-primary-foreground)',
                            fontSize: 13,
                            cursor: 'pointer',
                        }}
                    >
                        执行计划
                    </button>
                </div>
            )}
        </div>
    )
}
