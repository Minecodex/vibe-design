import { test, expect } from '@playwright/test'

test.describe('UX and Advanced Features', () => {
    test('should redirect unauthenticated user to login', async ({ page }) => {
        // Try accessing a protected route
        await page.goto('/dashboard/settings')

        // Should be redirected to login
        await expect(page).toHaveURL(/\/login/)
        await expect(page.getByText('像素重组')).toBeVisible()
    })

    test('should switch language between Chinese and English', async ({ page }) => {
        await page.goto('/login')

        // Default text (Chinese)
        await expect(page.getByPlaceholder('邮箱地址', { exact: true })).toBeVisible()

        // Open language dropdown - AntD Dropdown defaults to hover
        await page.locator('.anticon-global').hover()

        // Wait for dropdown menu to be visible
        const langMenu = page.locator('.ant-dropdown-menu')
        await expect(langMenu).toBeVisible()

        // Click English option
        await langMenu.getByText('English').click()

        // Verify text changed to English
        await expect(page.getByPlaceholder('Email Address', { exact: true })).toBeVisible()
        await expect(page.locator('button[type="submit"]')).toContainText('Sign In')

        // Switch back to Chinese
        await page.locator('.anticon-global').hover()
        await expect(langMenu).toBeVisible()
        await langMenu.getByText('中文').click()

        // Verify text changed back to Chinese
        await expect(page.getByPlaceholder('邮箱地址', { exact: true })).toBeVisible()
    })

})


