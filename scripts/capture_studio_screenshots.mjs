/**
 * Capture current-product Studio screenshots for README / docs.
 *
 * Prerequisites (from repo root):
 *   python3 -m queuewright_studio
 *   cd studio-ui && npm run dev
 *
 * Run:
 *   node --import ./studio-ui/node_modules/@playwright/test/index.mjs \
 *     scripts/capture_studio_screenshots.mjs
 * Or from studio-ui:
 *   node ../scripts/capture_studio_screenshots.mjs
 */
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const outDir = path.join(root, 'docs', 'screenshots')
const baseURL = process.env.STUDIO_URL ?? 'http://127.0.0.1:5173'

async function loadPlaywright() {
  try {
    return await import('@playwright/test')
  } catch {
    return await import('../studio-ui/node_modules/@playwright/test/index.mjs')
  }
}

async function waitForStudio(page) {
  await page.goto(baseURL, { waitUntil: 'networkidle' })
  await page.getByLabel('qWright', { exact: true }).waitFor({
    state: 'visible',
    timeout: 30_000,
  })
  await page.waitForTimeout(600)
}

async function selectServiceStudent(page) {
  await page.getByRole('button', { name: 'Services' }).click()
  await page.getByRole('heading', { name: 'Build your service structure' }).waitFor({
    timeout: 15_000,
  })
  const student = page.locator('.tree-row', { hasText: 'Student Services' }).first()
  if (await student.isVisible().catch(() => false)) {
    await student.click()
  }
  await page.waitForTimeout(500)
}

async function openReadiness(page) {
  await page.getByRole('button', { name: 'Readiness' }).click()
  await page.waitForTimeout(700)
}

async function main() {
  const { chromium } = await loadPlaywright()
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  try {
    {
      const context = await browser.newContext({
        viewport: { width: 1600, height: 1000 },
        deviceScaleFactor: 1,
      })
      const page = await context.newPage()
      await waitForStudio(page)
      await openReadiness(page)
      await page.screenshot({
        path: path.join(outDir, 'studio-readiness.png'),
        fullPage: false,
      })
      await context.close()
      console.log('wrote studio-readiness.png')
    }

    {
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true,
      })
      const page = await context.newPage()
      await waitForStudio(page)
      await selectServiceStudent(page)
      await page.screenshot({
        path: path.join(outDir, 'studio-mobile.png'),
        fullPage: false,
      })
      await context.close()
      console.log('wrote studio-mobile.png')
    }

    console.log(`Screenshots written to ${outDir}`)
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
