import { expect, test } from '@playwright/test'

test('edits plan-backed settings and unlocks export after local compilation', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle('qWright')
  await expect(page.getByLabel('qWright', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Organization' }).click()
  await page.getByLabel('Service owner role').fill('Head of Service Management')

  await page.getByRole('button', { name: 'Services' }).click()
  await expect(page.getByRole('heading', { name: 'Build your service structure' })).toBeVisible()
  await page.getByRole('switch', { name: 'Customer entry point' }).click()

  await page.getByRole('button', { name: 'Policies' }).click()
  await page.getByRole('group', { name: 'Cross-department handoff capability' }).click()
  await page.getByRole('checkbox', { name: 'sanitized child' }).uncheck()

  await page.getByRole('button', { name: 'Governance' }).click()
  await expect(page.locator('.governance-row')).toHaveCount(19)
  await expect(page.getByText('Unsupported', { exact: true }).first()).toBeVisible()

  await page.getByRole('button', { name: 'Readiness' }).click()
  await expect(page.getByRole('heading', { name: 'Check readiness honestly' })).toBeVisible()
  await expect(page.getByText(/The studio cannot deliver these capabilities/)).toBeVisible()

  await page.getByRole('button', { name: 'Review' }).click()
  await expect(page.getByText('Blueprint validated for local export')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Blueprint' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Project', exact: true })).toBeEnabled()
})
