import { useState, useEffect } from 'react'
import { Copy, Eye, Search, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { billingApi, type UsageLogRead, type UsageLogListRead, type UsageLogSummaryRead, type HarnessBillingSummary, type HarnessBillingModelStat } from '@/api/endpoints/billing'
import { useAuthStore } from '@/store/authStore'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { ResultPreviewDialog } from './ResultPreviewDialog'
import { usersApi, type User as UserType } from '@/api/endpoints/users'
import { getImageUrl } from '@/utils/imageUrl'
import { formatCnyFromCents } from '@/utils/money'
import { getModelDisplayName } from '@/utils/modelDisplayName'
import {
    Dialog,
    DialogContent,
    DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'

interface BillingModalProps {
    open: boolean
    onCancel: () => void
}

interface UsageTypeFilterOption {
    value: string
    labelKey: string
    taskType?: string
    billingLabel?: string
}

interface ChildUsageModelCallStat {
    model_name: string
    model_label: string
    calls: number
    success_calls: number
    failed_calls: number
}

// Status styles mapping
const STATUS_STYLES: Record<string, string> = {
    success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    failed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    blocked: 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-300',
    refunded: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    cancelled: 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400',
}

const TASK_TYPE_LABEL_KEYS: Record<string, string> = {
    text2image: 'billing.labels.image_generate',
    text2video: 'billing.labels.video_generate',
    image2video: 'billing.labels.video_generate',
    multimodal: 'billing.labels.multimodal_call',
    agent: 'billing.labels.agent_call',
    mark_recognition: 'billing.labels.mark_recognition',
    spatial_angle: 'billing.labels.spatial_angle',
    text_recognition: 'billing.labels.text_recognition',
    text_redraw: 'billing.labels.text_redraw',
    image_erase: 'billing.labels.image_erase',
    hd_upscale: 'billing.labels.hd_upscale',
}

const USAGE_TYPE_FILTERS: UsageTypeFilterOption[] = [
    { value: 'text2image', labelKey: 'billing.labels.image_generate', taskType: 'text2image' },
    { value: 'text2video', labelKey: 'billing.labels.video_generate', taskType: 'text2video' },
    { value: 'billing.labels.reference_decision', labelKey: 'billing.labels.reference_decision', billingLabel: 'billing.labels.reference_decision' },
    { value: 'billing.labels.smart_designer', labelKey: 'billing.labels.smart_designer', billingLabel: 'billing.labels.smart_designer' },
    { value: 'billing.labels.web_generate', labelKey: 'billing.labels.web_generate', billingLabel: 'billing.labels.web_generate' },
    { value: 'billing.labels.document_generate', labelKey: 'billing.labels.document_generate', billingLabel: 'billing.labels.document_generate' },
    { value: 'billing.labels.ppt_generate', labelKey: 'billing.labels.ppt_generate', billingLabel: 'billing.labels.ppt_generate' },
    { value: 'billing.labels.spreadsheet_generate', labelKey: 'billing.labels.spreadsheet_generate', billingLabel: 'billing.labels.spreadsheet_generate' },
    { value: 'mark_recognition', labelKey: 'billing.labels.mark_recognition', taskType: 'mark_recognition' },
    { value: 'spatial_angle', labelKey: 'billing.labels.spatial_angle', taskType: 'spatial_angle' },
    { value: 'text_recognition', labelKey: 'billing.labels.text_recognition', taskType: 'text_recognition' },
    { value: 'text_redraw', labelKey: 'billing.labels.text_redraw', taskType: 'text_redraw' },
    { value: 'image_erase', labelKey: 'billing.labels.image_erase', taskType: 'image_erase' },
    { value: 'hd_upscale', labelKey: 'billing.labels.hd_upscale', taskType: 'hd_upscale' },
    { value: 'multimodal', labelKey: 'billing.labels.multimodal_call', taskType: 'multimodal' },
]

function formatDateTime(iso: string) {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatElapsed(elapsedMs: number | null, created: string, updated: string): string {
    if (elapsedMs != null && elapsedMs > 0) {
        return elapsedMs >= 1000 ? `${(elapsedMs / 1000).toFixed(1)}s` : `${elapsedMs}ms`
    }
    const diff = Math.round((new Date(updated).getTime() - new Date(created).getTime()) / 1000)
    return diff > 0 ? `${diff}s` : '-'
}

function getPaginationItems(currentPage: number, totalPages: number): (number | string)[] {
    if (totalPages <= 7) {
        return Array.from({ length: totalPages }, (_, i) => i + 1)
    }

    const res: (number | string)[] = []
    res.push(1)
    
    if (currentPage <= 4) {
        res.push(2, 3, 4, 5, '...', totalPages)
    } else if (currentPage >= totalPages - 3) {
        res.push('...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages)
    } else {
        res.push('...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages)
    }
    
    return res
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null
}

function isStringArray(value: unknown): value is string[] {
    return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isHarnessBillingModelStatArray(value: unknown): value is HarnessBillingModelStat[] {
    return Array.isArray(value) && value.every((item) => (
        isObjectRecord(item)
        && typeof item.model_name === 'string'
        && typeof item.model_label === 'string'
        && typeof item.calls === 'number'
        && typeof item.success_calls === 'number'
        && typeof item.failed_calls === 'number'
    ))
}

function isHarnessBillingSummary(value: unknown): value is HarnessBillingSummary {
    if (!isObjectRecord(value)) {
        return false
    }

    return (
        typeof value.mode === 'string'
        && typeof value.mode_label === 'string'
        && typeof value.multimodal_calls === 'number'
        && (value.image_analysis_calls === undefined || typeof value.image_analysis_calls === 'number')
        && typeof value.image_generation_calls === 'number'
        && typeof value.video_generation_calls === 'number'
        && isStringArray(value.multimodal_models)
        && (value.image_analysis_models === undefined || isStringArray(value.image_analysis_models))
        && isStringArray(value.image_models)
        && isStringArray(value.video_models)
        && (value.multimodal_model_stats === undefined || isHarnessBillingModelStatArray(value.multimodal_model_stats))
        && (value.image_analysis_model_stats === undefined || isHarnessBillingModelStatArray(value.image_analysis_model_stats))
        && (value.image_model_stats === undefined || isHarnessBillingModelStatArray(value.image_model_stats))
        && (value.video_model_stats === undefined || isHarnessBillingModelStatArray(value.video_model_stats))
        && typeof value.total_elapsed_ms === 'number'
    )
}

function getUsageTypeFilterParams(filterValue: string): { task_type?: string; billing_label?: string } {
    const matchedFilter = USAGE_TYPE_FILTERS.find((item) => item.value === filterValue)
    if (!matchedFilter) {
        return { task_type: filterValue }
    }

    return matchedFilter.billingLabel
        ? { billing_label: matchedFilter.billingLabel }
        : { task_type: matchedFilter.taskType }
}

function getBillingSummary(params: UsageLogSummaryRead | null | undefined): HarnessBillingSummary | null {
    if (!params) {
        return null
    }

    return isHarnessBillingSummary(params.billing_summary) ? params.billing_summary : null
}

function hasChildUsage(row: UsageLogListRead): boolean {
    const kind = getRowUsageKind(row)
    return row.task_type === 'agent' || kind === 'agent_parent'
}

function formatElapsedFromMs(elapsedMs: number | null | undefined): string {
    if (!elapsedMs || elapsedMs <= 0) {
        return '-'
    }
    return elapsedMs >= 1000 ? `${(elapsedMs / 1000).toFixed(1)}s` : `${elapsedMs}ms`
}

function normalizeUsageStatus(status: string | null | undefined): string {
    const normalized = String(status || '').trim().toLowerCase()
    if (normalized === 'completed' || normalized === 'succeeded') {
        return 'success'
    }
    return normalized
}

function isFailedUsageStatus(status: string | null | undefined): boolean {
    return ['failed', 'blocked', 'refunded', 'cancelled'].includes(normalizeUsageStatus(status))
}

function getRowUsageKind(row: UsageLogRead | UsageLogListRead | null): string | null {
    if (!row) return null
    const params = ((row as { params?: Record<string, unknown> | null }).params ?? null) as Record<string, unknown> | null
    return String(row.kind || params?.kind || '')
}

function toUsageTokenCount(value: unknown): number {
    const parsed = Number(value ?? 0)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

function getUsageTokenCounts(params: Record<string, unknown> | null | undefined): {
    inputTokens: number
    outputTokens: number
} {
    const detail = isObjectRecord(params?.detail) ? params.detail : null
    return {
        inputTokens: toUsageTokenCount(params?.input_tokens ?? detail?.input_tokens),
        outputTokens: toUsageTokenCount(params?.output_tokens ?? detail?.output_tokens),
    }
}

function getUsageModelDisplayName(row: Pick<UsageLogRead | UsageLogListRead, 'model_label' | 'model_name'>): string {
    return getModelDisplayName(row.model_label, row.model_name)
}

function getModelStats(
    summary: HarnessBillingSummary,
    kind: 'multimodal' | 'image_analysis' | 'image_generation' | 'video_generation',
): HarnessBillingModelStat[] {
    if (kind === 'multimodal') {
        return summary.multimodal_model_stats ?? summary.multimodal_models.map((modelName) => ({
            model_name: modelName,
            model_label: modelName,
            calls: 0,
            success_calls: 0,
            failed_calls: 0,
        }))
    }
    if (kind === 'image_analysis') {
        return summary.image_analysis_model_stats ?? (summary.image_analysis_models ?? []).map((modelName) => ({
            model_name: modelName,
            model_label: modelName,
            calls: 0,
            success_calls: 0,
            failed_calls: 0,
        }))
    }
    if (kind === 'image_generation') {
        return summary.image_model_stats ?? summary.image_models.map((modelName) => ({
            model_name: modelName,
            model_label: modelName,
            calls: 0,
            success_calls: 0,
            failed_calls: 0,
        }))
    }
    return summary.video_model_stats ?? summary.video_models.map((modelName) => ({
        model_name: modelName,
        model_label: modelName,
        calls: 0,
        success_calls: 0,
        failed_calls: 0,
    }))
}

function mergeChildUsageModelStat(
    current: Map<string, ChildUsageModelCallStat>,
    stat: ChildUsageModelCallStat,
) {
    const key = stat.model_name || stat.model_label
    if (!key) {
        return
    }

    const existing = current.get(key)
    if (existing) {
        existing.calls += stat.calls
        existing.success_calls += stat.success_calls
        existing.failed_calls += stat.failed_calls
        if (!existing.model_label && stat.model_label) {
            existing.model_label = stat.model_label
        }
        return
    }

    current.set(key, { ...stat })
}

function getSummaryModelCallStats(summary: HarnessBillingSummary | null): ChildUsageModelCallStat[] {
    if (!summary) {
        return []
    }

    const stats = new Map<string, ChildUsageModelCallStat>()
    const summaryStats = [
        ...(summary.multimodal_model_stats ?? []),
        ...(summary.image_analysis_model_stats ?? []),
        ...(summary.image_model_stats ?? []),
        ...(summary.video_model_stats ?? []),
    ]

    for (const item of summaryStats) {
        mergeChildUsageModelStat(stats, {
            model_name: item.model_name,
            model_label: item.model_label,
            calls: item.calls,
            success_calls: item.success_calls,
            failed_calls: item.failed_calls,
        })
    }

    return Array.from(stats.values())
        .filter((item) => item.calls > 0 || item.success_calls > 0 || item.failed_calls > 0)
        .sort((a, b) => getModelDisplayName(a.model_label, a.model_name).localeCompare(getModelDisplayName(b.model_label, b.model_name)))
}

function getChildUsageModelCallStats(
    summary: HarnessBillingSummary | null,
    rows: UsageLogRead[],
): ChildUsageModelCallStat[] {
    const summaryStats = getSummaryModelCallStats(summary)
    if (summaryStats.length > 0) {
        return summaryStats
    }

    const stats = new Map<string, ChildUsageModelCallStat>()
    for (const row of rows) {
        if (getRowUsageKind(row) === 'subagent') {
            continue
        }

        const modelName = String(row.model_name || '').trim()
        const modelLabel = String(row.model_label || modelName).trim()
        if (!modelName && !modelLabel) {
            continue
        }

        const normalizedStatus = normalizeUsageStatus(row.status)
        mergeChildUsageModelStat(stats, {
            model_name: modelName || modelLabel,
            model_label: modelLabel || modelName,
            calls: 1,
            success_calls: normalizedStatus === 'success' ? 1 : 0,
            failed_calls: isFailedUsageStatus(normalizedStatus) ? 1 : 0,
        })
    }

    return Array.from(stats.values())
        .sort((a, b) => getModelDisplayName(a.model_label, a.model_name).localeCompare(getModelDisplayName(b.model_label, b.model_name)))
}

export function BillingModal({ open, onCancel }: BillingModalProps) {
    const { t } = useTranslation()
    const user = useAuthStore(s => s.user)
    const providerBalanceSyncEnabled = useAuthStore(s => s.providerBalanceSyncEnabled)
    const isAdmin = user?.role === 'admin'
    const showLocalAmounts = !providerBalanceSyncEnabled
    const usageColumnCount = 7 + (isAdmin ? 1 : 0) + (showLocalAmounts ? 1 : 0)

    // ── Usage tab state ──
    const [usageLoading, setUsageLoading] = useState(false)
    const [usageData, setUsageData] = useState<UsageLogListRead[]>([])
    const [usageTotal, setUsageTotal] = useState(0)
    const [usagePage, setUsagePage] = useState(1)
    const [usagePageSize, setUsagePageSize] = useState(10)
    const [taskIdFilter, setTaskIdFilter] = useState('')
    const [typeFilter, setTypeFilter] = useState<string>('')
    const [statusFilter, setStatusFilter] = useState<string>('')
    const [userIdFilter, setUserIdFilter] = useState<string>('')

    // ── Result preview ──
    const [previewOpen, setPreviewOpen] = useState(false)
    const [previewTaskId, setPreviewTaskId] = useState<number | null>(null)
    const [childUsageOpen, setChildUsageOpen] = useState(false)
    const [childUsageLoading, setChildUsageLoading] = useState(false)
    const [childUsageParent, setChildUsageParent] = useState<UsageLogListRead | null>(null)
    const [childUsageSummary, setChildUsageSummary] = useState<UsageLogSummaryRead | null>(null)
    const [childUsageData, setChildUsageData] = useState<UsageLogRead[]>([])
    const [childUsageExpandedIds, setChildUsageExpandedIds] = useState<Record<number, boolean>>({})
    const [childUsageNestedLoadingIds, setChildUsageNestedLoadingIds] = useState<Record<number, boolean>>({})
    const [childUsageNestedData, setChildUsageNestedData] = useState<Record<number, UsageLogRead[]>>({})

    // ── User search for admin ──
    const [userSearchText, setUserSearchText] = useState('')
    const [usersList, setUsersList] = useState<UserType[]>([])
    const [userSearchLoading, setUserSearchLoading] = useState(false)

    const fetchUsage = async () => {
        setUsageLoading(true)
        try {
            const params: Record<string, unknown> = {
                page: usagePage,
                page_size: usagePageSize,
            }
            if (taskIdFilter) params.task_id = parseInt(taskIdFilter) || undefined
            if (typeFilter) Object.assign(params, getUsageTypeFilterParams(typeFilter))
            if (statusFilter) params.status = statusFilter
            if (isAdmin && userIdFilter) params.user_id = parseInt(userIdFilter) || 0

            const res = await billingApi.getUsageLogs(params as Parameters<typeof billingApi.getUsageLogs>[0])
            setUsageData(res.data.items)
            setUsageTotal(res.data.total)
        } catch {
            toast.error(t('billing.fetch_usage_failed'))
        } finally {
            setUsageLoading(false)
        }
    }

    useEffect(() => {
        if (open) fetchUsage()
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, usagePage, usagePageSize, taskIdFilter, typeFilter, statusFilter, userIdFilter])

    useEffect(() => {
        if (isAdmin && userSearchText) {
            const timer = setTimeout(async () => {
                setUserSearchLoading(true)
                try {
                    const res = await usersApi.getUsers({ search: userSearchText, page_size: 50 })
                    setUsersList(res.data.items)
                } finally {
                    setUserSearchLoading(false)
                }
            }, 300)
            return () => clearTimeout(timer)
        } else if (isAdmin && !userSearchText) {
            setUsersList([])
        }
    }, [userSearchText, isAdmin])

    const copyTaskId = (taskId: string) => {
        navigator.clipboard.writeText(taskId).then(() => toast.success(t('common.copied')))
    }

    const openPreview = (taskId: number) => {
        setPreviewTaskId(taskId)
        setPreviewOpen(true)
    }

    const openChildUsage = async (row: UsageLogListRead) => {
        setChildUsageParent(row)
        setChildUsageSummary(null)
        setChildUsageOpen(true)
        setChildUsageExpandedIds({})
        setChildUsageNestedLoadingIds({})
        setChildUsageNestedData({})
        setChildUsageData([])
        setChildUsageLoading(true)
        try {
            const summaryRes = await billingApi.getUsageLogSummary(row.id)
            const billingSummary = getBillingSummary(summaryRes.data)
            if (billingSummary) {
                setChildUsageSummary(summaryRes.data)
            }
            const res = await billingApi.getUsageLogChildren(row.id)
            setChildUsageData(res.data.items)
        } catch {
            toast.error(t('billing.fetch_usage_failed'))
            setChildUsageData([])
        } finally {
            setChildUsageLoading(false)
        }
    }

    const usageTotalPages = Math.max(1, Math.ceil(usageTotal / usagePageSize))

    const translateBillingLabel = (billingLabel: string) => {
        if (billingLabel === 'billing.labels.prompt_extraction') {
            return t('billing.labels.prompt_extraction', '提示词提取')
        }
        const translated = t(billingLabel)
        return translated === billingLabel ? billingLabel : translated
    }

    const getTaskTypeLabel = (taskType: string) => {
        const labelKey = TASK_TYPE_LABEL_KEYS[taskType]
        return labelKey ? t(labelKey) : taskType
    }

    const getUsageKind = (row: UsageLogRead | UsageLogListRead | null) => {
        return getRowUsageKind(row)
    }

    const getSubagentLabel = (row: UsageLogRead | UsageLogListRead | null) => {
        if (!row) return null
        const params = ((row as { params?: Record<string, unknown> | null }).params ?? null) as Record<string, unknown> | null
        return String(row.subagent_label || params?.subagent_label || '').trim() || null
    }

    const getRequestId = (row: UsageLogRead | null) => {
        if (!row) return null
        const params = (row.params ?? null) as Record<string, unknown> | null
        const providerBill = (params?.provider_bill ?? null) as Record<string, unknown> | null
        const generationTask = (params?.generation_task ?? null) as Record<string, unknown> | null
        const value = (
            params?.oneapi_request_id
            || providerBill?.oneapi_request_id
            || params?.request_id
            || providerBill?.request_id
            || params?.external_task_id
            || generationTask?.external_task_id
            || generationTask?.request_id
        )
        const text = String(value || '').trim()
        return text || null
    }

    const getUsageLabel = (row: UsageLogRead | UsageLogListRead | null) => {
        if (!row) return getTaskTypeLabel('agent')
        if (getUsageKind(row) === 'subagent') return getSubagentLabel(row) || t('billing.labels.subagent', '下游机器人')
        if (row.billing_label) return translateBillingLabel(row.billing_label)
        return getTaskTypeLabel(row.task_type)
    }

    const renderUsageStatus = (status: string) => {
        const normalizedStatus = normalizeUsageStatus(status)
        return normalizedStatus === 'success' ? t('billing.status_success', '成功') :
            normalizedStatus === 'failed' ? t('billing.status_failed', '失败') :
                normalizedStatus === 'refunded' ? t('billing.status_refunded', '已退款') :
                    normalizedStatus === 'pending' ? t('billing.status_pending', '处理中') :
                        normalizedStatus === 'blocked' ? t('billing.status_blocked', '已阻塞') :
                            normalizedStatus === 'cancelled' ? t('billing.status_cancelled', '已中断') :
                                normalizedStatus.toUpperCase()
    }

    const childUsageHarnessSummary = getBillingSummary(childUsageSummary)
    const childUsageModelStats = getChildUsageModelCallStats(childUsageHarnessSummary, childUsageData)
    const childUsageModelCalls = childUsageModelStats.reduce((total, item) => total + item.calls, 0)
    const harnessSummaryItems = childUsageHarnessSummary ? [
        {
            key: 'multimodal',
            label: t('billing.summary.multimodal_calls', '多模态模型调用'),
            value: childUsageHarnessSummary.multimodal_calls,
            models: getModelStats(childUsageHarnessSummary, 'multimodal'),
        },
        {
            key: 'image_analysis',
            label: t('billing.summary.image_analysis_calls', '图片分析模型调用'),
            value: childUsageHarnessSummary.image_analysis_calls ?? 0,
            models: getModelStats(childUsageHarnessSummary, 'image_analysis'),
        },
        {
            key: 'image_generation',
            label: t('billing.summary.image_generation_calls', '图片生成模型调用'),
            value: childUsageHarnessSummary.image_generation_calls,
            models: getModelStats(childUsageHarnessSummary, 'image_generation'),
        },
        {
            key: 'video_generation',
            label: t('billing.summary.video_generation_calls', '视频生成模型调用'),
            value: childUsageHarnessSummary.video_generation_calls,
            models: getModelStats(childUsageHarnessSummary, 'video_generation'),
        },
    ] : []

    const toggleChildUsageRow = async (row: UsageLogRead) => {
        if (getUsageKind(row) !== 'subagent') {
            return
        }

        const nextExpanded = !childUsageExpandedIds[row.id]
        setChildUsageExpandedIds((current) => ({
            ...current,
            [row.id]: nextExpanded,
        }))

        if (!nextExpanded || childUsageNestedData[row.id]) {
            return
        }

        setChildUsageNestedLoadingIds((current) => ({
            ...current,
            [row.id]: true,
        }))
        try {
            const res = await billingApi.getUsageLogChildren(row.id)
            setChildUsageNestedData((current) => ({
                ...current,
                [row.id]: res.data.items,
            }))
        } catch {
            toast.error(t('billing.fetch_usage_failed'))
            setChildUsageNestedData((current) => ({
                ...current,
                [row.id]: [],
            }))
        } finally {
            setChildUsageNestedLoadingIds((current) => ({
                ...current,
                [row.id]: false,
            }))
        }
    }

    return (
        <>
            <Dialog open={open} onOpenChange={(v) => { if (!v) onCancel() }}>
                <DialogContent noDarken className={cn(
                    "max-w-[90vw] sm:max-w-[1000px] max-h-[92vh] overflow-hidden p-0 border flex flex-col glass-modal-unified"
                )}>
                    <div className="flex flex-shrink-0 items-center justify-between border-b border-[var(--app-border)] p-6 pb-4">
                        <div>
                            <DialogTitle className="text-xl font-bold text-foreground">
                                {t('billing.task_log', '任务日志')}
                            </DialogTitle>
                            <p className="text-sm text-muted-foreground mt-0.5">
                                {t('billing.description', '您的图像、视频和音频生成任务记录')}
                            </p>
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto px-6 pb-6 mt-6">
                            <div>
                                {/* Filters */}
                                <div className="flex items-center gap-3 mb-6 flex-wrap">
                                    <div className="relative">
                                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                        <Input
                                            placeholder={t('billing.filter_task_id', '输入任务ID进行筛选')}
                                            className="w-[220px] pl-9"
                                            value={taskIdFilter}
                                            onChange={(e) => { setTaskIdFilter(e.target.value); setUsagePage(1) }}
                                        />
                                    </div>
                                    <Select value={typeFilter} onValueChange={(v) => { setTypeFilter(v === 'all' ? '' : v); setUsagePage(1) }}>
                                        <SelectTrigger className="w-[140px]">
                                            <SelectValue placeholder={t('billing.all_types', '所有类型')} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="all">{t('billing.all_types', '所有类型')}</SelectItem>
                                            {USAGE_TYPE_FILTERS.map((filterOption) => (
                                                <SelectItem key={filterOption.value} value={filterOption.value}>
                                                    {t(filterOption.labelKey)}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v === 'all' ? '' : v); setUsagePage(1) }}>
                                        <SelectTrigger className="w-[140px]">
                                            <SelectValue placeholder={t('billing.all_status', '所有状态')} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="all">{t('billing.all_status', '所有状态')}</SelectItem>
                                            <SelectItem value="success">{t('billing.status_success', '成功')}</SelectItem>
                                            <SelectItem value="failed">{t('billing.status_failed', '失败')}</SelectItem>
                                            <SelectItem value="refunded">{t('billing.status_refunded', '已退款')}</SelectItem>
                                            <SelectItem value="pending">{t('billing.status_pending', '处理中')}</SelectItem>
                                            <SelectItem value="blocked">{t('billing.status_blocked', '已阻塞')}</SelectItem>
                                            <SelectItem value="cancelled">{t('billing.status_cancelled', '已中断')}</SelectItem>
                                        </SelectContent>
                                    </Select>
                                    {isAdmin && (
                                        <Select 
                                            value={userIdFilter || 'all'} 
                                            onValueChange={(v) => { setUserIdFilter(v === 'all' ? '' : v); setUsagePage(1) }}
                                        >
                                            <SelectTrigger className="w-[180px]">
                                                <SelectValue placeholder={t('billing.filter_user', '搜索用户')} />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <div className="p-2">
                                                    <Input
                                                        placeholder={t('billing.search_user_hint', '搜索用户名/昵称...')}
                                                        className="h-8 mb-2"
                                                        value={userSearchText}
                                                        onChange={(e) => setUserSearchText(e.target.value)}
                                                        onKeyDown={(e) => e.stopPropagation()}
                                                    />
                                                </div>
                                                <SelectItem value="all">{t('billing.all_users', '所有用户')}</SelectItem>
                                                {userSearchLoading && <div className="text-center py-2 text-xs text-muted-foreground">{t('common.searching')}</div>}
                                                {usersList.map((u) => (
                                                    <SelectItem key={u.id} value={String(u.id)}>
                                                        <div className="flex items-center gap-2">
                                                            <div className="w-5 h-5 rounded-full overflow-hidden bg-muted flex-shrink-0">
                                                                {u.avatar_url ? (
                                                                    <img src={getImageUrl(u.avatar_url)} className="w-full h-full object-cover" />
                                                                ) : (
                                                                    <div className="w-full h-full flex items-center justify-center text-[10px] bg-primary text-primary-foreground">
                                                                        {u.nickname?.[0] || u.username[0]}
                                                                    </div>
                                                                )}
                                                            </div>
                                                            <span className="truncate">{u.nickname || u.username}</span>
                                                        </div>
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    )}
                                    <Button variant="ghost" size="icon" onClick={fetchUsage} className="h-9 w-9 rounded-full">
                                        <RefreshCw className="w-4 h-4" />
                                    </Button>
                                </div>

                                {/* Usage Table */}
                                <div className="overflow-hidden rounded-[var(--app-radius-lg)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] shadow-sm">
                                    <Table>
                                        <TableHeader className="sticky top-0 z-10">
                                            <TableRow className="hover:bg-transparent">
                                                <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight">{t('billing.col_time', '时间')}</TableHead>
                                                {isAdmin && <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight">{t('billing.col_user', '用户')}</TableHead>}
                                                <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight">{t('billing.col_type', '类型')}</TableHead>
                                                <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight">{t('billing.col_model', '模型')}</TableHead>
                                                <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight">{t('billing.col_status', '状态')}</TableHead>
                                                {showLocalAmounts && (
                                                    <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight text-right">{t('billing.col_cost', '价格')}</TableHead>
                                                )}
                                                <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight">{t('billing.col_duration', '时长')}</TableHead>
                                                <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight">{t('billing.col_task_id', '任务 ID')}</TableHead>
                                                <TableHead className="font-bold text-[12px] text-[var(--app-foreground-subtle)] h-14 uppercase tracking-tight">{t('billing.col_result', '结果')}</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {usageLoading ? (
                                                <TableRow>
                                                    <TableCell colSpan={usageColumnCount} className="text-center py-12 text-muted-foreground italic">
                                                        {t('common.loading', '加载中...')}
                                                    </TableCell>
                                                </TableRow>
                                            ) : usageData.length === 0 ? (
                                                <TableRow>
                                                    <TableCell colSpan={usageColumnCount} className="text-center py-12 text-muted-foreground">
                                                        {t('common.no_data', '暂无数据')}
                                                    </TableCell>
                                                </TableRow>
                                            ) : usageData.map((row) => (
                                                <TableRow key={row.id}>
                                                    <TableCell className="text-[12px] whitespace-nowrap text-[var(--app-foreground-subtle)] font-medium py-5">{formatDateTime(row.created_at)}</TableCell>
                                                    {isAdmin && (
                                                        <TableCell className="min-w-[80px]">
                                                            <div className="flex items-center gap-2 py-1">
                                                                <div className="w-6 h-6 rounded-full overflow-hidden bg-muted border border-[var(--app-border)] shrink-0">
                                                                    {row.avatar_url ? (
                                                                        <img src={getImageUrl(row.avatar_url)} alt={row.nickname} className="w-full h-full object-cover" />
                                                                    ) : (
                                                                        <div className="w-full h-full flex items-center justify-center text-[10px] bg-primary/10 text-primary uppercase">
                                                                            {row.nickname?.[0] || 'U'}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                                <span className="text-[11px] font-semibold truncate max-w-[80px]" title={row.nickname || String(row.user_id)}>
                                                                    {row.nickname || `ID: ${row.user_id}`}
                                                                </span>
                                                            </div>
                                                        </TableCell>
                                                    )}
                                                    <TableCell>
                                                        <span className={cn(
                                                            "inline-flex items-center rounded-full bg-[var(--app-surface-muted)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-foreground"
                                                        )}>
                                                            {getUsageLabel(row)}
                                                        </span>
                                                    </TableCell>
                                                    <TableCell>
                                                        <span className="text-[11px] font-bold text-[var(--app-foreground-muted)]">
                                                            {getUsageModelDisplayName(row)}
                                                        </span>
                                                    </TableCell>
                                                    <TableCell>
                                                        {(() => {
                                                            const normalizedStatus = normalizeUsageStatus(row.status)
                                                            return (
                                                        <span className={cn(
                                                            'inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold shadow-sm',
                                                            STATUS_STYLES[normalizedStatus] || 'bg-gray-100 text-gray-700'
                                                        )}>
                                                            {renderUsageStatus(row.status)}
                                                        </span>
                                                            )
                                                        })()}
                                                    </TableCell>
                                                    {showLocalAmounts && (
                                                        <TableCell className="font-bold text-[13px] text-right">
                                                            {formatCnyFromCents(row.amount_cents)}
                                                        </TableCell>
                                                    )}
                                                    <TableCell className="text-[12px] text-[var(--app-foreground-subtle)]">
                                                        {formatElapsed(row.elapsed_ms, row.created_at, row.updated_at)}
                                                    </TableCell>
                                                    <TableCell>
                                                        {row.task_id ? (
                                                            <div className="flex items-center gap-1 group">
                                                                <span className="text-[11px] font-mono truncate max-w-[80px] text-[var(--app-foreground-subtle)]">
                                                                    {row.task_id}
                                                                </span>
                                                                <button
                                                                    onClick={() => copyTaskId(String(row.task_id))}
                                                                    className="rounded-md p-1 transition-colors hover:bg-[var(--app-control-hover)]"
                                                                >
                                                                    <Copy className="w-3 h-3 text-muted-foreground group-hover:text-foreground" />
                                                                </button>
                                                            </div>
                                                        ) : '-'}
                                                    </TableCell>
                                                    <TableCell>
                                                        {hasChildUsage(row) ? (
                                                            <button
                                                                onClick={() => openChildUsage(row)}
                                                                className="flex items-center gap-1 text-[12px] font-bold text-blue-500 hover:text-blue-400 transition-colors"
                                                            >
                                                                <Eye className="w-3.5 h-3.5" /> {showLocalAmounts ? t('billing.view_child_costs', '查看子账单') : t('billing.view_child_usage', '查看明细')}
                                                            </button>
                                                        ) : normalizeUsageStatus(row.status) === 'success' && row.task_id ? (
                                                            <button
                                                                onClick={() => openPreview(row.task_id!)}
                                                                className="flex items-center gap-1 text-[12px] font-bold text-blue-500 hover:text-blue-400 transition-colors"
                                                            >
                                                                <Eye className="w-3.5 h-3.5" /> {t('common.view', '查看')}
                                                            </button>
                                                        ) : row.status === 'failed' || row.status === 'refunded' ? (
                                                            <span className="text-[11px] text-red-500/80 truncate max-w-[120px] block font-medium">
                                                                {row.status === 'refunded' ? t('billing.status_refunded', '已退款') : t('billing.status_failed', '失败')}
                                                            </span>
                                                        ) : '-'}
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </div>

                                {/* Pagination */}
                                <div className="flex items-center justify-between mt-6 px-2">
                                    <span className="text-[12px] text-muted-foreground">
                                        {t('common.total')} <span className="font-bold text-foreground">{usageTotal}</span> {t('common.items')}
                                    </span>
                                    <div className="flex items-center gap-4">
                                        <div className="flex items-center gap-1">
                                            <Button 
                                                variant="ghost" 
                                                size="icon" 
                                                disabled={usagePage <= 1} 
                                                onClick={() => setUsagePage(p => p - 1)}
                                                className="h-8 w-8 rounded-full"
                                            >
                                                &lt;
                                            </Button>
                                            {getPaginationItems(usagePage, usageTotalPages).map((p, i) => {
                                                const isCurrent = p === usagePage;
                                                const isDots = p === '...';
                                                return (
                                                    <button
                                                        key={i}
                                                        disabled={isDots}
                                                        onClick={() => !isDots && typeof p === 'number' && setUsagePage(p)}
                                                        className={cn(
                                                            "inline-flex items-center justify-center min-w-[32px] h-8 px-2 rounded-xl text-[12px] font-bold transition-all",
                                                            isCurrent
                                                                ? "bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)] shadow-sm"
                                                                : isDots
                                                                    ? "cursor-default text-[var(--app-foreground-subtle)]"
                                                                    : "text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground"
                                                        )}
                                                    >
                                                        {p}
                                                    </button>
                                                );
                                            })}
                                            <Button 

                                                variant="ghost" 
                                                size="icon" 
                                                disabled={usagePage >= usageTotalPages} 
                                                onClick={() => setUsagePage(p => p + 1)}
                                                className="h-8 w-8 rounded-full"
                                            >
                                                &gt;
                                            </Button>
                                        </div>
                                        <Select value={String(usagePageSize)} onValueChange={(v) => { setUsagePageSize(Number(v)); setUsagePage(1) }}>
                                            <SelectTrigger className="h-8 w-[80px] text-[11px] font-bold">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent className="rounded-xl">
                                                <SelectItem value="10">10 {t('common.per_page')}</SelectItem>
                                                <SelectItem value="20">20 {t('common.per_page')}</SelectItem>
                                                <SelectItem value="50">50 {t('common.per_page')}</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </div>
                    </div>
                </DialogContent>
            </Dialog>

            <Dialog open={childUsageOpen} onOpenChange={setChildUsageOpen}>
                <DialogContent noDarken className="max-w-[720px] max-h-[80vh] overflow-hidden p-0 flex flex-col">
                    <div className="shrink-0 border-b border-[var(--app-border)] p-6 pb-4">
                        <DialogTitle className="text-lg font-bold">
                            {showLocalAmounts ? t('billing.child_usage_title', '子费用明细') : t('billing.child_usage_detail_title', '子用量明细')}
                        </DialogTitle>
                        <p className="text-sm text-muted-foreground mt-1">
                            {getUsageLabel(childUsageParent)}
                        </p>
                    </div>
                    <div data-testid="child-usage-scroll-area" className="p-6 flex-1 min-h-0 overflow-y-auto overscroll-contain">
                        {childUsageLoading ? (
                            <div className="text-center py-8 text-muted-foreground">
                                {t('common.loading', '加载中...')}
                            </div>
                        ) : childUsageData.length > 0 ? (
                            <div className="space-y-3">
                                {childUsageModelStats.length > 0 && (
                                    <div
                                        data-testid="child-usage-model-stats"
                                        className="rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4"
                                    >
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="text-sm font-semibold">
                                                {t('billing.child_usage_model_stats_title', '模型调用统计')}
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                {t('billing.child_usage_model_stats_total', { defaultValue: '共 {{count}} 次', count: childUsageModelCalls })}
                                            </div>
                                        </div>
                                        <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                            {childUsageModelStats.map((item) => {
                                                const displayName = getModelDisplayName(item.model_label, item.model_name)

                                                return (
                                                    <div
                                                        key={item.model_name || item.model_label}
                                                        className="rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-surface)] px-3 py-2"
                                                    >
                                                        <div className="flex items-start justify-between gap-3">
                                                            <div className="min-w-0">
                                                                <div className="truncate text-sm font-semibold" title={displayName}>
                                                                    {displayName}
                                                                </div>
                                                                <div className="mt-1 text-xs text-muted-foreground">
                                                                    {item.calls} {t('billing.summary.calls_unit', '次')}
                                                                </div>
                                                            </div>
                                                            <div className="flex shrink-0 flex-col items-end gap-1 text-xs font-semibold">
                                                                <span className="text-green-600 dark:text-green-400">
                                                                    {t('billing.summary.success_calls', '成功')} {item.success_calls}
                                                                </span>
                                                                <span className="text-red-600 dark:text-red-400">
                                                                    {t('billing.summary.failed_calls', '失败')} {item.failed_calls}
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    </div>
                                )}
                                {childUsageData.map((row) => {
                                    const params = row.params as Record<string, unknown> | null
                                    const { inputTokens, outputTokens } = getUsageTokenCounts(params)
                                    const requestId = getRequestId(row)
                                    const tokenSummary = inputTokens > 0 || outputTokens > 0
                                        ? t('billing.token_summary', { defaultValue: '输入 {{input}} / 输出 {{output}}', input: inputTokens, output: outputTokens })
                                        : null
                                    const isSubagentRow = getUsageKind(row) === 'subagent'
                                    const nestedRows = childUsageNestedData[row.id] || []
                                    const isExpanded = !!childUsageExpandedIds[row.id]
                                    const isNestedLoading = !!childUsageNestedLoadingIds[row.id]

                                    return (
                                        <div
                                            key={row.id}
                                            className="rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4"
                                        >
                                            <div className="flex items-start justify-between gap-4">
                                                <div className="min-w-0">
                                                    <div className="text-sm font-semibold">
                                                        {getUsageLabel(row)}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground mt-1">
                                                        {isSubagentRow ? t('billing.labels.subagent', '下游机器人') : getUsageModelDisplayName(row)}
                                                    </div>
                                                    {tokenSummary && (
                                                        <div className="text-xs text-muted-foreground mt-2">
                                                            {tokenSummary}
                                                        </div>
                                                    )}
                                                    {requestId && (
                                                        <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground min-w-0">
                                                            <span className="shrink-0">{t('billing.request_id', '请求ID')}</span>
                                                            <span className="font-mono truncate">{requestId}</span>
                                                            <button
                                                                type="button"
                                                                onClick={() => copyTaskId(requestId)}
                                                                className="rounded-md p-1 transition-colors hover:bg-[var(--app-control-hover)]"
                                                                aria-label={t('billing.copy_request_id', '复制请求ID')}
                                                            >
                                                                <Copy className="w-3 h-3" />
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="text-right shrink-0">
                                                    {showLocalAmounts && (
                                                        <div className="text-sm font-bold">{formatCnyFromCents(row.amount_cents)}</div>
                                                    )}
                                                    <div className="text-xs text-muted-foreground mt-1">
                                                        {formatElapsed(row.elapsed_ms, row.created_at, row.updated_at)}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="mt-3">
                                                <span className={cn(
                                                    'inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold shadow-sm',
                                                    STATUS_STYLES[normalizeUsageStatus(row.status)] || 'bg-gray-100 text-gray-700'
                                                )}>
                                                    {renderUsageStatus(row.status)}
                                                </span>
                                            </div>
                                            {isSubagentRow && (
                                                <div className="mt-3">
                                                    <button
                                                        type="button"
                                                        onClick={() => toggleChildUsageRow(row)}
                                                        aria-label={`展开下游机器人 ${getUsageLabel(row)}`}
                                                        className="text-xs font-semibold text-blue-500 hover:text-blue-400 transition-colors"
                                                    >
                                                        {isExpanded ? t('common.collapse', '收起') : t('common.expand', '展开')}
                                                    </button>
                                                </div>
                                            )}
                                            {isSubagentRow && isExpanded && (
                                                <div className="ml-3 mt-3 space-y-3 border-l border-[var(--app-border)] pl-3">
                                                    {isNestedLoading ? (
                                                        <div className="text-xs text-muted-foreground">
                                                            {t('common.loading', '加载中...')}
                                                        </div>
                                                    ) : nestedRows.map((childRow) => {
                                                        const childParams = childRow.params as Record<string, unknown> | null
                                                        const { inputTokens: childInputTokens, outputTokens: childOutputTokens } = getUsageTokenCounts(childParams)
                                                        const childRequestId = getRequestId(childRow)
                                                        const childTokenSummary = childInputTokens > 0 || childOutputTokens > 0
                                                            ? t('billing.token_summary', { defaultValue: '输入 {{input}} / 输出 {{output}}', input: childInputTokens, output: childOutputTokens })
                                                            : null

                                                        return (
                                                            <div
                                                                key={childRow.id}
                                                                className="rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] p-3"
                                                            >
                                                                <div className="flex items-start justify-between gap-4">
                                                                    <div className="min-w-0">
                                                                        <div className="text-sm font-semibold">
                                                                            {getUsageLabel(childRow)}
                                                                        </div>
                                                                        <div className="text-xs text-muted-foreground mt-1">
                                                                            {getUsageModelDisplayName(childRow)}
                                                                        </div>
                                                                        {childTokenSummary && (
                                                                            <div className="text-xs text-muted-foreground mt-2">
                                                                                {childTokenSummary}
                                                                            </div>
                                                                        )}
                                                                        {childRequestId && (
                                                                            <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground min-w-0">
                                                                                <span className="shrink-0">{t('billing.request_id', '请求ID')}</span>
                                                                                <span className="font-mono truncate">{childRequestId}</span>
                                                                                <button
                                                                                    type="button"
                                                                                    onClick={() => copyTaskId(childRequestId)}
                                                                                    className="rounded-md p-1 transition-colors hover:bg-[var(--app-control-hover)]"
                                                                                    aria-label={t('billing.copy_request_id', '复制请求ID')}
                                                                                >
                                                                                    <Copy className="w-3 h-3" />
                                                                                </button>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                    <div className="text-right shrink-0">
                                                                        {showLocalAmounts && (
                                                                            <div className="text-sm font-bold">{formatCnyFromCents(childRow.amount_cents)}</div>
                                                                        )}
                                                                        <div className="text-xs text-muted-foreground mt-1">
                                                                            {formatElapsed(childRow.elapsed_ms, childRow.created_at, childRow.updated_at)}
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                                <div className="mt-3">
                                                        <span className={cn(
                                                            'inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold shadow-sm',
                                                            STATUS_STYLES[normalizeUsageStatus(childRow.status)] || 'bg-gray-100 text-gray-700'
                                                        )}>
                                                            {renderUsageStatus(childRow.status)}
                                                        </span>
                                                                </div>
                                                            </div>
                                                        )
                                                    })}
                                                </div>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        ) : childUsageHarnessSummary ? (
                            <div data-testid="harness-billing-summary" className="space-y-4">
                                <div className="rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4">
                                    <div className="text-sm font-semibold">
                                        {t('billing.summary.mode_label', '模式')}
                                    </div>
                                    <div className="mt-2 text-lg font-bold">
                                        {childUsageHarnessSummary.mode_label}
                                    </div>
                                    <div className="mt-2 text-xs text-muted-foreground">
                                        {t('billing.summary.total_elapsed', '总耗时')} {formatElapsedFromMs(childUsageHarnessSummary.total_elapsed_ms)}
                                    </div>
                                </div>
                                <div className="grid gap-3 sm:grid-cols-3">
                                    {harnessSummaryItems.map((item) => (
                                        <div
                                            key={item.key}
                                            className="rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] p-4"
                                        >
                                            <div className="text-xs text-muted-foreground">
                                                {item.label}
                                            </div>
                                            <div className="mt-2 text-2xl font-bold">
                                                {item.value}
                                                <span className="ml-1 text-sm font-medium text-muted-foreground">
                                                    {t('billing.summary.calls_unit', '次')}
                                                </span>
                                            </div>
                                            {item.models.length > 0 && (
                                                <div className="mt-3 space-y-2 text-xs text-muted-foreground break-words">
                                                    {item.models.map((model) => (
                                                        <div key={`${item.key}-${model.model_name}`} className="rounded-[var(--app-radius-sm)] border border-[var(--app-border)] px-3 py-2">
                                                            <div>
                                                                {t('billing.summary.used_models', '使用模型')} {getModelDisplayName(model.model_label, model.model_name)}
                                                            </div>
                                                            <div className="mt-1 flex gap-3">
                                                                <span>{t('billing.summary.success_calls', '成功')} {model.success_calls}</span>
                                                                <span>{t('billing.summary.failed_calls', '失败')} {model.failed_calls}</span>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : childUsageData.length === 0 ? (
                            <div className="text-center py-8 text-muted-foreground">
                                {t('common.no_data', '暂无数据')}
                            </div>
                        ) : null}
                    </div>
                </DialogContent>
            </Dialog>
            <ResultPreviewDialog 
                open={previewOpen} 
                onOpenChange={setPreviewOpen} 
                taskId={previewTaskId} 
            />
        </>
    )
}


