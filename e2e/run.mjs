/* Browser end-to-end tests against a running Flowly stack (real browser, real API, real database).

   BASE_URL=https://yourdomain.com ADMIN_TOKEN=... node run.mjs
   Optional: CHROME_PATH (defaults to the system Chrome/Edge). Test data uses the e2e-*@example.test address
   pattern so it can be removed afterwards:  manage.py purge_e2e  (see backend/apps/leads/management).
   The suite submits 3 requests, so it stays under the 8/hour public rate limit. */
import {chromium} from 'playwright-core';
import {existsSync} from 'node:fs';
import assert from 'node:assert/strict';

const BASE = (process.env.BASE_URL || 'http://127.0.0.1:3000').replace(/\/$/, '');
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || '';
const RUN = Date.now().toString(36);
const EMAIL = `e2e-${RUN}@example.test`;
const candidates = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '/usr/bin/google-chrome', '/usr/bin/chromium'].filter(Boolean);
const executablePath = candidates.find(existsSync);
assert(executablePath, 'No Chrome/Edge found; set CHROME_PATH');

const results = [];
const consoleProblems = [];
async function step(name, fn) {
  try { await fn(); results.push([name, true]); console.log('PASS ' + name); }
  catch (e) { results.push([name, false, e]); console.log('FAIL ' + name + '\n     ' + String(e.message).split('\n')[0]); }
}
function watch(page) {
  page.on('pageerror', e => consoleProblems.push(`pageerror ${page.url()} ${e.message}`));
  page.on('console', m => { if (m.type() === 'error' && !/favicon|Failed to load resource.*(401|404|409|429)/.test(m.text())) consoleProblems.push(`console ${page.url()} ${m.text()}`); });
  page.on('requestfailed', r => { if (!/analytics/.test(r.url())) consoleProblems.push(`requestfailed ${r.url()} ${r.failure()?.errorText}`); });
}
function futureWorkday(offset) {
  const d = new Date(); d.setUTCDate(d.getUTCDate() + offset);
  while ([5, 6].includes(d.getUTCDay())) d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

const browser = await chromium.launch({executablePath, headless: true});
const ctx = await browser.newContext({viewport: {width: 1366, height: 900}, ignoreHTTPSErrors: false});
const page = await ctx.newPage();
watch(page);
let contactRef = '', consultRef = '', consultDate = '', consultTime = '';

// ---------------------------------------------------------------- public site
await step('home renders hero, header, footer and no runtime errors', async () => {
  const r = await page.goto(BASE + '/', {waitUntil: 'networkidle'});
  assert.equal(r.status(), 200);
  assert.match(await page.title(), /flowly/i);
  assert((await page.locator('h1').first().innerText()).length > 10);
  assert(await page.locator('footer a[href="/account/"]').count() === 1, 'footer account link');
});

const routes = ['/services', '/industries', '/government', '/about', '/approach', '/engagement', '/pricing', '/insights', '/start',
  '/consultation', '/contact', '/status', '/support', '/procurement', '/responsible-ai', '/accessibility', '/privacy', '/terms',
  '/security', '/services/ai-erp', '/services/private-ai', '/industries/healthcare', '/insights/', '/team'];
await step(`all ${routes.length} routes render a heading without errors`, async () => {
  const failures = [];
  for (const route of routes) {
    const r = await page.goto(BASE + route, {waitUntil: 'domcontentloaded'});
    await page.waitForSelector('h1,h2', {timeout: 8000}).catch(() => {});
    const h = await page.locator('h1').count();
    if (r.status() !== 200 || h === 0) failures.push(`${route} status=${r.status()} h1=${h}`);
  }
  assert.equal(failures.join('; '), '', 'route failures');
});

await step('every internal link on the home page resolves (no dead navigation)', async () => {
  await page.goto(BASE + '/', {waitUntil: 'networkidle'});
  const links = [...new Set(await page.$$eval('a[href^="/"]', as => as.map(a => a.getAttribute('href').split('#')[0])))].filter(h => !h.startsWith('/api'));
  const bad = [];
  for (const href of links) {
    const r = await page.request.get(BASE + href);
    if (r.status() >= 400) bad.push(href + ' ' + r.status());
  }
  assert.equal(bad.join(', '), '', `checked ${links.length} links`);
});

await step('service search/filter works on /services', async () => {
  await page.goto(BASE + '/services', {waitUntil: 'networkidle'});
  const before = await page.locator('a[href^="/services/"]').count();
  const box = page.locator('input[type="search"],input[placeholder*="earch"],input[placeholder*="بحث"]').first();
  await box.fill('ERP');
  await page.waitForTimeout(400);
  const after = await page.locator('a[href^="/services/"]').count();
  assert(after > 0 && after < before, `filtered ${before} -> ${after}`);
});

await step('language switches to Arabic (RTL) and persists; theme toggles dark', async () => {
  await page.goto(BASE + '/', {waitUntil: 'networkidle'});
  await page.locator('.language-button').click();
  assert.equal(await page.evaluate(() => document.documentElement.dir), 'rtl');
  assert.equal(await page.evaluate(() => document.documentElement.lang), 'ar');
  await page.reload({waitUntil: 'networkidle'});
  assert.equal(await page.evaluate(() => document.documentElement.dir), 'rtl', 'persisted across reload');
  await page.locator('.theme-button').click();
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark');
  await page.locator('.language-button').click();
  await page.locator('.theme-button').click();
  assert.equal(await page.evaluate(() => document.documentElement.dir), 'ltr');
});

await step('assistant opens, answers from the catalog and links to a real service', async () => {
  await page.goto(BASE + '/', {waitUntil: 'networkidle'});
  await page.locator('.assistant-trigger').click();
  await page.locator('.assistant-foot input').fill('I need an AI ERP');
  await page.locator('.assistant-foot button[type=submit]').click();
  await page.waitForSelector('.chat-message.assistant', {timeout: 15000});
  const href = await page.locator('.chat-link').first().getAttribute('href');
  assert.match(href, /^\/services\//);
  const r = await page.request.get(BASE + href);
  assert.equal(r.status(), 200);
});

// -------------------------------------------------------------------- intake
await step('contact form validates, then saves a request and shows a reference', async () => {
  await page.goto(BASE + '/contact', {waitUntil: 'networkidle'});
  await page.locator('input[name=name]').fill('E2E Contact');
  await page.locator('input[name=email]').fill(EMAIL);
  await page.locator('input[name=organization]').fill('E2E Org ' + RUN);
  await page.locator('textarea[name=requirements]').fill('Too short');
  await page.locator('.consent input').check();
  await page.locator('button[type=submit]').click();
  assert(await page.evaluate(() => !document.querySelector('form').checkValidity()), 'short requirements blocked by validation');
  await page.locator('textarea[name=requirements]').fill('E2E test: connect our inventory spreadsheets with an automated weekly operations report.');
  await page.locator('button[type=submit]').click();
  await page.waitForSelector('.receipt strong', {timeout: 15000});
  contactRef = (await page.locator('.receipt strong').innerText()).trim();
  assert.match(contactRef, /^FLW-\d{8}-[A-F0-9]{8}$/);
});

await step('consultation: booked slot becomes unavailable to the next visitor', async () => {
  consultDate = futureWorkday(9);
  consultTime = '12:00';
  await page.goto(BASE + '/consultation', {waitUntil: 'networkidle'});
  await page.locator('input[name=name]').fill('E2E Consult');
  await page.locator('input[name=email]').fill(EMAIL);
  await page.locator('input[name=organization]').fill('E2E Consult Org ' + RUN);
  await page.locator('textarea[name=requirements]').fill('E2E test: we want a discovery conversation about automating customer onboarding.');
  // move calendar to the target month if needed and pick the date
  // Find the first date/time that is still free (earlier runs may have booked some slots).
  let found = false;
  for (let offset = 9; offset < 60 && !found; offset++) {
    const candidate = futureWorkday(offset);
    const busy = (await (await page.request.get(BASE + '/api/availability?date=' + candidate)).json()).busy || [];
    const free = ['10:00', '11:00', '12:00', '14:00', '15:00'].find(x => !busy.includes(x));
    if (free) { consultDate = candidate; consultTime = free; found = true; }
  }
  assert(found, 'no free consultation slot in the next 60 days');
  for (let i = 0; i < 4 && !(await page.locator(`button[aria-label="${consultDate}"]`).count()); i++) {
    await page.locator('button[aria-label="Next month"]').click();
  }
  await page.locator(`button[aria-label="${consultDate}"]`).click();
  await page.locator('.time-slots button', {hasText: new RegExp('^' + consultTime)}).click();
  await page.locator('.consent input').check();
  await page.locator('button[type=submit]').click();
  await page.waitForSelector('.receipt strong', {timeout: 15000});
  consultRef = (await page.locator('.receipt strong').innerText()).trim();
  assert.match(await page.locator('.receipt-time').innerText(), new RegExp(consultDate));
  assert.match(await page.locator('.receipt').innerText(), /receipt with your reference is emailed/);
  // a second visitor sees the slot as booked
  const other = await ctx.newPage();
  await other.goto(BASE + '/consultation', {waitUntil: 'networkidle'});
  for (let i = 0; i < 4 && !(await other.locator(`button[aria-label="${consultDate}"]`).count()); i++) {
    await other.locator('button[aria-label="Next month"]').click();
  }
  await other.locator(`button[aria-label="${consultDate}"]`).click();
  const slot = other.locator('.time-slots button', {hasText: new RegExp('^' + consultTime)});
  await slot.waitFor();
  assert(await slot.isDisabled(), 'booked slot is disabled');
  assert.match(await slot.innerText(), /booked/);
  await other.close();
});

await step('discovery wizard completes 5 steps and saves', async () => {
  await page.goto(BASE + '/start', {waitUntil: 'networkidle'});
  await page.locator('.choice').first().click();
  await page.locator('button.primary', {hasText: /Continue/}).click();
  await page.locator('.goal-choice').first().click();
  await page.locator('button.primary', {hasText: /Continue/}).click();
  await page.locator('textarea[name=requirements]').fill('E2E test: we want to modernise our manual reporting and approvals workflow.');
  await page.locator('button.primary', {hasText: /Continue/}).click();
  assert((await page.locator('.recommendations a').count()) >= 2, 'recommendations shown');
  await page.locator('button.primary', {hasText: /connect/i}).click();
  await page.locator('input[name=name]').fill('E2E Wizard');
  await page.locator('input[name=email]').fill(EMAIL);
  await page.locator('input[name=organization]').fill('E2E Wizard Org ' + RUN);
  await page.locator('.consent input').check();
  await page.locator('button[type=submit]').click();
  await page.waitForSelector('.receipt strong', {timeout: 15000});
});

await step('status page: wrong email is rejected, correct email shows the stage', async () => {
  await page.goto(BASE + '/status', {waitUntil: 'networkidle'});
  await page.locator('input[placeholder^="FLW"]').fill(contactRef);
  await page.locator('input[type=email]').fill('someone-else@example.test');
  await page.locator('button[type=submit]').click();
  await page.waitForSelector('.form-error');
  await page.locator('input[type=email]').fill(EMAIL);
  await page.locator('button[type=submit]').click();
  await page.waitForSelector('.status-result');
  assert.match(await page.locator('.status-result h2').innerText(), /Awaiting team review/);
});

// -------------------------------------------------------------- team console
await step('team console: rejects anonymous, unlocks with token, updates status, shows history', async () => {
  assert(ADMIN_TOKEN, 'ADMIN_TOKEN env var required');
  const t = await ctx.newPage();
  watch(t);
  await t.goto(BASE + '/team', {waitUntil: 'domcontentloaded'});
  await t.waitForSelector('.team-auth');
  assert.equal(await t.locator('.team-row').count(), 0, 'no data without credentials');
  await t.locator('input[minlength="32"]').fill('x'.repeat(40));
  await t.locator('button', {hasText: 'Unlock requests'}).click();
  await t.waitForSelector('[role=alert].form-error');
  await t.locator('input[minlength="32"]').fill(ADMIN_TOKEN);
  await t.locator('button', {hasText: 'Unlock requests'}).click();
  await t.waitForSelector('.team-row', {timeout: 15000});
  await t.locator('.team-toolbar input').fill(contactRef);
  await t.locator('.team-row').first().click();
  await t.locator('.team-detail select').selectOption('in_review');
  await t.locator('.team-detail textarea').fill('E2E internal note');
  await t.locator('button', {hasText: 'Save follow-up'}).click();
  await t.waitForSelector('.team-notice');
  // History reloads after saving; wait for the new entry rather than the stale list.
  await t.locator('.team-history li', {hasText: /status changed/i}).first().waitFor({timeout: 15000});
  assert.match(await t.locator('.team-history').innerText(), /in review/i);
  await t.close();
});

await step('customer sees the new status but never the internal note', async () => {
  await page.goto(BASE + '/status', {waitUntil: 'networkidle'});
  await page.locator('input[placeholder^="FLW"]').fill(contactRef);
  await page.locator('input[type=email]').fill(EMAIL);
  await page.locator('button[type=submit]').click();
  await page.waitForSelector('.status-result');
  const text = await page.locator('.status-result').innerText();
  assert.match(text, /In review/);
  assert(!text.includes('E2E internal note'));
});

// ---------------------------------------------------------- account & dashboard
await step('account portal: register, sign in, see the dashboard, edit profile, change password, sign out', async () => {
  const a = await ctx.newPage();
  watch(a);
  const accountEmail = `e2e-acct-${RUN}@example.test`;
  const pw = 'E2e-Passw0rd!' + RUN;
  await a.goto(BASE + '/account/#register', {waitUntil: 'networkidle'});
  await a.locator('#first_name').fill('Eve');
  await a.locator('#email').fill(accountEmail);
  await a.locator('#password').fill(pw);
  await a.locator('#password_confirm').fill(pw);
  await a.locator('button[type=submit]').click();
  await a.waitForSelector('.msg.ok');
  await a.goto(BASE + '/account/#login', {waitUntil: 'networkidle'});
  await a.locator('#email').fill(accountEmail);
  await a.locator('#password').fill(pw);
  await a.locator('button[type=submit]').click();
  await a.waitForSelector('text=Recent requests', {timeout: 15000});
  assert.match(await a.locator('h1').first().innerText(), /Eve/);
  await a.locator('nav a', {hasText: 'Profile'}).click();
  await a.locator('#first_name').first().fill('Evelyn');
  await a.locator('button', {hasText: 'Save profile'}).click();
  await a.waitForSelector('.msg.ok');
  await a.locator('#current_password').fill(pw);
  await a.locator('#new_password').fill(pw + 'x');
  await a.locator('button', {hasText: 'Change password'}).click();
  await a.waitForSelector('.msg.ok >> nth=1', {timeout: 10000}).catch(() => {});
  await a.locator('nav button', {hasText: 'Sign out'}).click();
  await a.waitForSelector('text=Sign in');
  // old password no longer works, new one does
  await a.locator('#email').fill(accountEmail);
  await a.locator('#password').fill(pw);
  await a.locator('button[type=submit]').click();
  await a.waitForSelector('[role=alert]');
  await a.locator('#password').fill(pw + 'x');
  await a.locator('button[type=submit]').click();
  await a.waitForSelector('text=Recent requests');
  await a.close();
});

await step('dashboard lists requests linked to a signed-in customer', async () => {
  const b = await ctx.newPage();
  watch(b);
  const email = `e2e-dash-${RUN}@example.test`;
  const pw = 'E2e-Passw0rd!' + RUN;
  const reg = await b.request.post(BASE + '/api/v1/auth/register/', {data: {email, password: pw, password_confirm: pw}});
  assert.equal(reg.status(), 201);
  const login = await (await b.request.post(BASE + '/api/v1/auth/login/', {data: {email, password: pw}})).json();
  const token = login.data.access;
  const submit = await b.request.post(BASE + '/api/v1/requests/', {
    headers: {Authorization: 'Bearer ' + token},
    data: {requestKey: crypto.randomUUID(), name: 'Dash User', email, organization: 'Dash Org', kind: 'contact', audience: 'business',
      requirements: 'E2E test: dashboard linkage check for authenticated submission.', consent: true, timezone: 'Africa/Cairo', language: 'en'}});
  assert.equal(submit.status(), 201);
  const mine = await (await b.request.get(BASE + '/api/v1/requests/mine/', {headers: {Authorization: 'Bearer ' + token}})).json();
  assert.equal(mine.data.count, 1);
  await b.close();
});

// ------------------------------------------------------------------ responsive
await step('mobile viewport: menu opens, no horizontal scroll, form usable', async () => {
  const m = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
  const p = await m.newPage();
  watch(p);
  await p.goto(BASE + '/', {waitUntil: 'networkidle'});
  await p.locator('.menu-button').click();
  assert(await p.locator('nav.mobile-open').count() === 1, 'mobile nav opens');
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert(overflow <= 1, 'horizontal overflow ' + overflow);
  await p.goto(BASE + '/contact', {waitUntil: 'networkidle'});
  assert(await p.locator('input[name=name]').isVisible());
  const overflow2 = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert(overflow2 <= 1, 'contact overflow ' + overflow2);
  await m.close();
});

await step('security: API docs open, anonymous admin API blocked, security headers present', async () => {
  const docs = await page.request.get(BASE + '/api/docs/');
  assert.equal(docs.status(), 200);
  assert.equal((await page.request.get(BASE + '/api/admin/requests')).status(), 401);
  assert.equal((await page.request.get(BASE + '/api/v1/admin/requests/')).status(), 401);
  assert.equal((await page.request.get(BASE + '/admin/')).status(), 200, '/admin/ is just the SPA, not the real admin'); // SPA fallback
  const html = await page.request.get(BASE + '/');
  const h = html.headers();
  assert.equal(h['x-content-type-options'], 'nosniff');
  if (BASE.startsWith('https')) assert(h['strict-transport-security'], 'HSTS');
});

await browser.close();

const failed = results.filter(r => !r[1]);
console.log('\n' + (results.length - failed.length) + '/' + results.length + ' browser checks passed');
console.log('requests: ' + [contactRef, consultRef].join(', '));
if (consoleProblems.length) {
  console.log('\nBrowser console/network problems (' + consoleProblems.length + '):');
  [...new Set(consoleProblems)].slice(0, 15).forEach(p => console.log('  - ' + p));
}
process.exit(failed.length || consoleProblems.length ? 1 : 0);
