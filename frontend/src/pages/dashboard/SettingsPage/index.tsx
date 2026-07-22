import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'

export function SettingsPage() {
  return (
    <div className="p-6 bg-transparent">
      <h4 className="text-lg font-semibold text-foreground">系统设置</h4>
      <p className="text-sm text-muted-foreground mb-4">系统设置，更多配置项敬请期待。</p>

      <div className="mt-4 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] p-6 shadow-[var(--app-shadow-control)]">
        <h5 className="font-medium text-foreground mb-4">基本设置</h5>
        <div className="space-y-4 max-w-[500px]">
          <div className="space-y-2">
            <Label>应用名称</Label>
            <Input defaultValue="像素重组" />
          </div>
          <div className="space-y-2">
            <Label>系统语言</Label>
            <Select defaultValue="zh-CN">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="zh-CN">简体中文</SelectItem>
                <SelectItem value="en-US">English</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-3">
            <Label>开启通知</Label>
            <Switch defaultChecked />
          </div>
          <Button>保存设置</Button>
        </div>
      </div>

      <Separator className="my-6" />

      <div className="rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] p-6 shadow-[var(--app-shadow-control)]">
        <h5 className="font-medium text-foreground mb-2">安全设置</h5>
        <p className="text-sm text-muted-foreground mb-4">双因素认证、登录日志等安全功能正在开发中。</p>
        <Button variant="outline" disabled>配置双因素认证（即将推出）</Button>
      </div>
    </div>
  )
}
