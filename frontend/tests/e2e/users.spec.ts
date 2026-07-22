import { test, expect } from '@playwright/test'

const testEmail = `user-nav-test-${Date.now()}@example.com`

test.describe('User Profile Flow', () => {
    test.beforeAll(async ({ browser }) => {
        // Register a test user
        const page = await browser.newPage()
        await page.goto('/register')
        await page.getByPlaceholder('邮箱地址').fill(testEmail)
        await page.locator('#register_username').fill('UserNavTest')
        await page.locator('#register_password').fill('Test1234!')
        await page.locator('#register_confirmPassword').fill('Test1234!')
        await page.locator('button[type="submit"]').click()
        await expect(page).toHaveURL(/\/login/)
        await page.close()
    })

    test.beforeEach(async ({ page }) => {
        // Login
        await page.goto('/login')
        await page.getByPlaceholder('邮箱地址').fill(testEmail)
        await page.getByPlaceholder('密码').fill('Test1234!')
        await page.locator('button[type="submit"]').click()
        await expect(page).toHaveURL(/\/dashboard/)
    })

    test('should navigate to user profile via header dropdown', async ({ page }) => {
        // Hover or click the user menu dropdown in the header to reveal "个人详情"
        // The dropdown trigger is the div wrapping the Avatar
        await page.locator('.ant-layout-header .ant-avatar').hover()

        // Click "个人详情"
        await page.locator('text=个人详情').click()

        // Expect navigation to user details
        await expect(page).toHaveURL(/\/dashboard\/users\/\d+/)
        await expect(page.locator('text=用户详情')).toBeVisible()
        await expect(page.locator('text=UserNavTest')).toBeVisible()
    })

    test('should upload and upate avatar from profile page', async ({ page }) => {
        // Go to profile
        await page.locator('.ant-layout-header .ant-avatar').hover()
        await page.locator('text=个人详情').click()
        await expect(page).toHaveURL(/\/dashboard\/users\/\d+/)

        // Listen for the file chooser (since clicking the Avatar with Upload component triggers a file chooser)
        const fileChooserPromise = page.waitForEvent('filechooser')

        // Click on the Avatar upload wrapper (the div wrapping the Avatar inside the Upload component)
        await page.locator('.ant-upload').click()

        const fileChooser = await fileChooserPromise
        await fileChooser.setFiles('tests/e2e/test_img.png')

        // Expect success message
        await expect(page.locator('text=头像上传成功')).toBeVisible()
    })

})
