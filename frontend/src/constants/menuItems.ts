export interface MenuItem {
  key: string
  label: string
  path: string
  icon: string
}

export const menuItems: MenuItem[] = [
  { key: 'overview', label: '首页', path: '/dashboard/overview', icon: 'HomeOutlined' },
  { key: 'reports', label: '生成', path: '/dashboard/reports', icon: 'BulbOutlined' },
  { key: 'projects', label: '项目', path: '/dashboard/projects', icon: 'ProjectOutlined' },
]
