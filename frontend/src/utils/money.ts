export function formatCnyFromCents(amountCents: number | null | undefined): string {
  const normalized = Number(amountCents ?? 0)
  return `¥${(normalized / 100).toFixed(2)}`
}
