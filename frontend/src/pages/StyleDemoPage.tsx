import { ImageIcon, LayoutGrid, Plus, Search, Trash2, Video } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { AppSurface, GlassPanel, IconButton, SegmentedControl, StatusBadge } from '@/components/common/ui'

export function StyleDemoPage() {
  const { t } = useTranslation()

  return (
    <div className="min-h-screen overflow-y-auto px-8 py-8 text-foreground">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-bold text-[var(--app-primary)]">{t('styleDemo.eyebrow')}</p>
          <h1 className="mt-2 text-4xl font-bold tracking-tight">{t('styleDemo.title')}</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            {t('styleDemo.subtitle')}
          </p>
        </div>
        <SegmentedControl
          aria-label={t('styleDemo.demoTabs')}
          value="all"
          onValueChange={() => undefined}
          options={[
            { key: 'all', label: t('projectDetails.all'), icon: LayoutGrid },
            { key: 'image', label: t('projectDetails.image'), icon: ImageIcon },
            { key: 'video', label: t('projectDetails.video'), icon: Video },
          ]}
        />
      </header>

      <div className="grid gap-5 lg:grid-cols-2">
        <GlassPanel className="p-5">
          <h2 className="mb-3 text-lg font-bold">{t('styleDemo.buttons')}</h2>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary"><Plus className="h-4 w-4" />{t('styleDemo.primary')}</Button>
            <Button>{t('styleDemo.secondary')}</Button>
            <Button variant="glass">{t('styleDemo.glass')}</Button>
            <Button variant="ghost">{t('styleDemo.ghost')}</Button>
            <Button variant="destructive"><Trash2 className="h-4 w-4" />{t('projectsPage.delete')}</Button>
            <IconButton aria-label="Icon action"><Search className="h-4 w-4" /></IconButton>
          </div>
        </GlassPanel>

        <GlassPanel className="p-5">
          <h2 className="mb-3 text-lg font-bold">{t('styleDemo.inputs')}</h2>
          <div className="grid gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-9" placeholder={t('styleDemo.searchPlaceholder')} />
            </div>
            <div className="flex flex-wrap gap-3">
              <Select defaultValue="10">
                <SelectTrigger className="w-[120px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">{t('styleDemo.pageSize', { count: 10 })}</SelectItem>
                  <SelectItem value="20">{t('styleDemo.pageSize', { count: 20 })}</SelectItem>
                </SelectContent>
              </Select>
              <div className="flex h-10 items-center gap-3 rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-control)] px-3">
                <span className="text-sm font-medium">{t('my_favorites')}</span>
                <Switch defaultChecked />
              </div>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel className="p-5 lg:col-span-2">
          <h2 className="mb-3 text-lg font-bold">{t('styleDemo.statusTable')}</h2>
          <div className="mb-4 flex flex-wrap gap-2">
            <StatusBadge variant="primary">{t('canvas.generating')}</StatusBadge>
            <StatusBadge variant="success">{t('projectDetails.active')}</StatusBadge>
            <StatusBadge variant="warning">{t('projectsPage.statusPending')}</StatusBadge>
            <StatusBadge variant="danger">{t('organization.status_disable')}</StatusBadge>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('users.labels.username')}</TableHead>
                <TableHead>{t('users.labels.email')}</TableHead>
                <TableHead>{t('organization.status')}</TableHead>
                <TableHead>{t('organization.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="font-semibold text-foreground">admin</TableCell>
                <TableCell>admin@admin.com</TableCell>
                <TableCell><StatusBadge variant="success">{t('organization.status_enable')}</StatusBadge></TableCell>
                <TableCell><Button variant="link">{t('organization.edit_user')}</Button></TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </GlassPanel>

        <AppSurface variant="panel" className="p-5 lg:col-span-2">
          <h2 className="mb-3 text-lg font-bold">{t('styleDemo.assetSurface')}</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[0, 1, 2, 3].map((item) => (
              <div key={item} className="aspect-square overflow-hidden rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-surface-solid)] shadow-sm">
                <img src="/src/image/homepage/design_showcase.png" alt="" className="h-full w-full object-cover" />
              </div>
            ))}
          </div>
        </AppSurface>

        <GlassPanel className="p-5 lg:col-span-2">
          <h2 className="mb-3 text-lg font-bold">{t('styleDemo.dialogMenu')}</h2>
          <div className="flex flex-wrap gap-3">
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="primary">{t('styleDemo.openDialog')}</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{t('organization.add_user')}</DialogTitle>
                </DialogHeader>
                <Input placeholder={t('users.labels.email')} />
                <DialogFooter>
                  <Button variant="outline">{t('common.cancel')}</Button>
                  <Button variant="primary">{t('common.confirm')}</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="glass">{t('styleDemo.openMenu')}</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem>{t('download')}</DropdownMenuItem>
                <DropdownMenuItem>{t('favorite')}</DropdownMenuItem>
                <DropdownMenuItem variant="destructive">{t('delete')}</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </GlassPanel>
      </div>
    </div>
  )
}
