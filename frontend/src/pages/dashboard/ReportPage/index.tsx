import { cn } from '@/lib/utils'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const data = [
  { key: 1, name: '月度销售报表', type: '销售', status: '已完成', updatedAt: '2024-01-31' },
  { key: 2, name: '用户增长分析', type: '用户', status: '已完成', updatedAt: '2024-01-28' },
  { key: 3, name: '季度财务报表', type: '财务', status: '生成中', updatedAt: '2024-01-15' },
  { key: 4, name: '运营数据周报', type: '运营', status: '已完成', updatedAt: '2024-01-22' },
]

export function ReportPage() {
  return (
    <div className="bg-transparent p-6">
      <h4 className="text-lg font-semibold text-foreground">报表中心</h4>
      <p className="text-sm text-muted-foreground mb-4">报表分析页，数据图表正在建设中，以下为示例数据。</p>

      <div className="mt-4 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] shadow-[var(--app-shadow-control)]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>报表名称</TableHead>
              <TableHead>类型</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>更新时间</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row) => (
              <TableRow key={row.key}>
                <TableCell>{row.name}</TableCell>
                <TableCell>{row.type}</TableCell>
                <TableCell>
                  <span className={cn(
                    'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                    row.status === '已完成'
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                  )}>
                    {row.status}
                  </span>
                </TableCell>
                <TableCell>{row.updatedAt}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
