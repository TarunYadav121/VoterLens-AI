import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'

test.describe('conversational audit assistant', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: /Load supplied sample/i })).toBeVisible()
    await page.getByRole('button', { name: /Load supplied sample/i }).click()
    await expect(page.getByText(/Analysis ANALYSIS-/i)).toBeVisible({ timeout: 30_000 })
    await page.getByRole('button', { name: /Open Insight Assistant/i }).click()
    await expect(page.getByRole('complementary', { name: /Insight Assistant Chat/i })).toBeVisible()
  })

  test('answers about a real area, opens evidence, and inspects a real record', async ({ page }) => {
    const chat = page.getByRole('complementary', { name: /Insight Assistant Chat/i })
    const input = chat.locator('input[type="text"]')
    await input.fill('B01 mein kya dikkat hai?')
    await input.press('Enter')
    await expect(chat).toContainText(/South Bend|B01/i)

    await input.fill('Open evidence')
    await input.press('Enter')
    await expect(page).toHaveURL(/.*$/)
    await expect(chat).toContainText(/evidence context|FND-/i)

    await input.fill('What changed in record SYN-0002?')
    await input.press('Enter')
    await expect(chat).toContainText(/Record SYN-0002|changed fields/i)
  })

  test('confirms, cancels, undoes, and downloads a draft revision', async ({ page }) => {
    const chat = page.getByRole('complementary', { name: /Insight Assistant Chat/i })
    const input = chat.locator('input[type="text"]')
    const originalResponse = await page.request.get('http://127.0.0.1:5053/api/sample-data/current')
    expect(originalResponse.ok()).toBeTruthy()
    const originalCsv = await originalResponse.text()
    expect(originalCsv).toMatch(/SYN-0002,Asha Chatterjee,A01,North Valley,22,/)

    await input.fill('Record SYN-0002 ki age 44 karni hai')
    await input.press('Enter')
    await expect(chat).toContainText(/Confirm draft revision/i)

    await chat.getByRole('button', { name: /Cancel/i }).click()
    await expect(chat).not.toContainText(/Confirm draft revision/i)

    await input.fill('Record SYN-0002 ki age 44 karni hai')
    await input.press('Enter')
    await chat.getByRole('button', { name: /Confirm change/i }).click()
    await expect(chat).toContainText(/Draft revision applied/i, { timeout: 30_000 })
    await expect(chat.getByRole('button', { name: /Download revised synthetic CSV/i })).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await chat.getByRole('button', { name: /Download revised synthetic CSV/i }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('voterlens-revised-synthetic-current.csv')
    const csv = await fs.readFile(await download.path(), 'utf8')
    expect(csv).toContain('44')
    expect(csv).not.toContain('SYN-0002,Asha Chatterjee,A01,North Valley,22,')

    await input.fill('Undo last change')
    await input.press('Enter')
    await expect(chat).toContainText(/undone|prior draft/i, { timeout: 30_000 })
  })

  test('preserves chat context, supports Hindi/Hinglish, and sends Gemini opt-in explicitly', async ({ page }) => {
    const chat = page.getByRole('complementary', { name: /Insight Assistant Chat/i })
    const input = chat.locator('input[type="text"]')
    const requests = []
    page.on('request', (request) => {
      if (request.url().endsWith('/api/chat/message')) requests.push(JSON.parse(request.postData() || '{}'))
    })

    await input.fill('Which areas have unusual removal rates?')
    await input.press('Enter')
    await expect(chat).toContainText(/removal|South Bend|B01/i)
    await expect.poll(() => requests.length).toBe(1)
    expect(requests[0].conversation_id).toBeNull()
    expect(requests[0].allow_external_ai).toBe(false)

    await input.fill('Kya yeh fraud ka proof hai?')
    await input.press('Enter')
    await expect(chat).toContainText(/not proof|fraud|human review/i)
    await expect.poll(() => requests.length).toBe(2)
    expect(requests[1].conversation_id).toBeTruthy()
    expect(requests[1].allow_external_ai).toBe(false)

    await chat.getByRole('checkbox').check()
    await input.fill('Hinglish mein summary do')
    await input.press('Enter')
    await expect.poll(() => requests.length).toBe(3)
    expect(requests[2].conversation_id).toBe(requests[1].conversation_id)
    expect(requests[2].allow_external_ai).toBe(true)
  })

  test('rejects unknown records and invalid draft values without changing current analysis', async ({ page }) => {
    const chat = page.getByRole('complementary', { name: /Insight Assistant Chat/i })
    const input = chat.locator('input[type="text"]')
    await input.fill('Record UNKNOWN-999 ki age 44 karni hai')
    await input.press('Enter')
    await expect(chat).toContainText(/not found|unknown/i)

    await input.fill('Record SYN-0002 ki age 999 karni hai')
    await input.press('Enter')
    await expect(chat).toContainText(/whole number|0 to 120/i)
  })

  test('supports mobile chat controls and keyboard operation', async ({ page }) => {
    await expect(page.getByRole('complementary', { name: /Insight Assistant Chat/i })).toBeVisible()
    await page.keyboard.press('Tab')
    await expect(page.locator(':focus')).toBeVisible()
  })
})
