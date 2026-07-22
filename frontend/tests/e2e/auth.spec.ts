import { test, expect } from '@playwright/test'

const testEmail = `test-${Date.now()}@example.com`

test.describe.serial('Authentication Flow', () => {
  test('should show login page by default', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByText('像素重组')).toBeVisible()
  })

  test('should navigate to register page', async ({ page }) => {
    await page.goto('/login')
    await page.getByText('立即注册').click()
    await expect(page).toHaveURL(/\/register/)
    await expect(page.getByText('注册账户')).toBeVisible()
  })

  test('should register a new user successfully', async ({ page }) => {
    await page.goto('/register')
    await page.getByPlaceholder('邮箱地址').fill(testEmail)
    await page.locator('#register_username').fill('TestUser')
    await page.locator('#register_password').fill('Test1234!')
    await page.locator('#register_confirmPassword').fill('Test1234!')
    await page.locator('button[type="submit"]').click()
    // It should redirect to login page with success message, wait until login URL
    await expect(page).toHaveURL(/\/login/)
  })


  test('should show validation errors on empty login submit', async ({ page }) => {
    await page.goto('/login')
    await page.locator('button[type="submit"]').click()
    await expect(page.getByText('请输入邮箱')).toBeVisible()
    await expect(page.getByText('请输入密码')).toBeVisible()
  })

  test('should show validation errors on empty register submit', async ({ page }) => {
    await page.goto('/register')
    await page.locator('button[type="submit"]').click()
    await expect(page.getByText('请输入邮箱')).toBeVisible()
  })

  test('should redirect to dashboard after login', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('邮箱地址').fill(testEmail)
    await page.getByPlaceholder('密码').fill('Test1234!')
    await page.locator('button[type="submit"]').click()
    await expect(page).toHaveURL(/\/dashboard/)
  })

  test('should show dashboard menu items after login', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('邮箱地址').fill(testEmail)
    await page.getByPlaceholder('密码').fill('Test1234!')
    await page.locator('button[type="submit"]').click()
    // Use menu-scoped locators to avoid strict mode violations with duplicate text on the page
    const menu = page.locator('.ant-menu')
    await expect(menu.getByText('概览', { exact: true })).toBeVisible()
    await expect(menu.getByText('报表', { exact: true })).toBeVisible()
    await expect(menu.getByText('系统设置', { exact: true })).toBeVisible()
  })

  test('should navigate between menu items', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('邮箱地址').fill(testEmail)
    await page.getByPlaceholder('密码').fill('Test1234!')
    await page.locator('button[type="submit"]').click()

    // Click 报表 menu item and verify navigation
    await page.locator('.ant-menu').getByText('报表', { exact: true }).click()
    await expect(page).toHaveURL(/\/dashboard\/reports/)
    await expect(page.getByText('报表中心')).toBeVisible()
  })
})
