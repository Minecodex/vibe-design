import { toast } from 'sonner'
import { formatCnyFromCents } from './money'

type TranslateFn = (key: string, defaultValue?: string) => string

const DEFAULT_INSUFFICIENT_BALANCE_MESSAGE = '余额不足，无法发起新对话'

export function ensureBalanceOrNotify(
  balanceCents: number | null | undefined,
  t: unknown,
  fallbackMessage = DEFAULT_INSUFFICIENT_BALANCE_MESSAGE,
): boolean {
  if ((balanceCents ?? 0) > 0) {
    return true
  }

  const translate = t as TranslateFn
  toast.error(translate('billing.insufficient', fallbackMessage))
  return false
}

export function isBalanceRequiredForMultimodalProvider(providerCode: string | null | undefined): boolean {
  return isBalanceRequiredForProvider(providerCode)
}

export function isBalanceRequiredForProvider(providerCode: string | null | undefined): boolean {
  return String(providerCode || '').trim().toLowerCase() !== 'ollama'
}

export function buildInsufficientBalanceMessage(requiredCents: number): string {
  return `余额不足，需要 ${formatCnyFromCents(requiredCents)}`
}

