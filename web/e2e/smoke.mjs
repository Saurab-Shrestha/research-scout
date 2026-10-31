// Browser smoke test against the running app. Needs the API on :8000 and `npm run dev` on :5173.
//   npm run e2e
// Creates one temporary tracker entry for the top opportunity and deletes it at the end.
import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const WEB = process.env.WEB_URL ?? 'http://localhost:5173'
const API = `${WEB}/api/v1`
const json = async (path, init) => (await fetch(`${API}${path}`, init)).json()

const [top] = await json('/opportunities')
assert.ok(top, 'needs at least one scored opportunity')
const existing = (await json('/applications')).find((a) => a.opportunity_id === top.id)
assert.ok(!existing, `${top.professor} is already tracked; the test would change your data`)
const app = await json('/applications', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ opportunity_id: top.id }) })
const status = async () => (await json('/applications')).find((a) => a.id === app.id).status

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
const step = (name) => console.log(`✓ ${name}`)

try {
  for (const [path, heading] of [['/', /Good (morning|afternoon|evening)/], ['/opportunities', 'Discover Opportunities'], ['/shortlist', 'My Shortlist'], ['/tracker', 'Application Tracker'],
    ['/drafts', 'Writing Studio'], ['/researchers', 'Researchers'], ['/profile', 'Academic Profile'], ['/settings', 'Settings']]) {
    await page.goto(WEB + path)
    await page.getByRole('heading', { level: 1, name: heading }).waitFor()
  }
  step('every page renders')

  await page.goto(`${WEB}/opportunities`)
  const box = page.locator('#q')
  for (const text of ['toronto', 'quantum']) {  // clearing then typing fast used to bring the old text back
    await box.fill(''); await box.pressSequentially(text, { delay: 10 })
  }
  await page.waitForTimeout(400)
  assert.equal(await box.inputValue(), 'quantum')
  assert.equal(new URL(page.url()).searchParams.get('q'), 'quantum')
  step('search box keeps exactly what was typed')

  await page.goto(`${WEB}/opportunities?opp=${top.id}`)
  await page.getByRole('dialog').getByRole('tab', { name: 'Funding' }).click()
  await page.getByRole('dialog').getByText('Evidence from official pages').waitFor()
  step('opportunity side panel opens from the URL')

  await page.goto(`${WEB}/tracker`)
  const card = page.getByRole('button', { name: new RegExp(`^${top.professor}`) }).first()
  const from = await card.boundingBox(), to = await page.getByRole('region', { name: 'Contacted' }).boundingBox()
  await page.mouse.move(from.x + 40, from.y + 20); await page.mouse.down()
  await page.mouse.move(from.x + 60, from.y + 30, { steps: 5 }); await page.mouse.move(to.x + 100, to.y + 120, { steps: 15 })
  await page.mouse.up(); await page.waitForTimeout(1000)
  assert.equal(await status(), 'contacted'); step('pointer drag moves a card')

  await page.getByRole('button', { name: new RegExp(`Move ${top.professor}`) }).focus()
  // dnd-kit attaches its keyboard listeners a tick after pick-up, so pause between keys like a person would
  for (const key of ['Space', 'ArrowRight', 'Space']) { await page.keyboard.press(key); await page.waitForTimeout(200) }
  await page.waitForTimeout(1000)
  assert.equal(await status(), 'replied'); step('keyboard drag moves a card one stage')

  await page.getByRole('button', { name: new RegExp(`^${top.professor}`) }).first().click()
  await page.getByRole('dialog').getByLabel('Notes').waitFor(); await page.keyboard.press('Escape')
  step('card opens the editor')

  await page.goto(`${WEB}/drafts?for=${top.id}`)
  await page.getByRole('heading', { level: 2, name: top.professor }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'I sent it' }).count(), 0, '"I sent it" must not move a replied application back')
  step('draft studio guards the tracker status')

  assert.deepEqual(errors, [], 'console errors'); step('no console errors')
} finally {
  await fetch(`${API}/applications/${app.id}`, { method: 'DELETE' })
  await browser.close()
}
