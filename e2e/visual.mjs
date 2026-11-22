/* Visual check of the account portal and admin dashboard: screenshots in EN/AR, light/dark, desktop/mobile.
   BASE_URL=http://127.0.0.1:5174 ADMIN_EMAIL=... ADMIN_PASSWORD=... node visual.mjs  -> e2e/screens/*.png */
import {chromium} from 'playwright-core';
import {existsSync, mkdirSync} from 'node:fs';

const BASE = (process.env.BASE_URL || 'http://127.0.0.1:5174').replace(/\/$/, '');
const exe = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
mkdirSync('screens', {recursive: true});
const browser = await chromium.launch({executablePath: exe, headless: true});
const problems = [];

async function shot(ctxOpts, prefs, path, name, after) {
  const ctx = await browser.newContext(ctxOpts);
  await ctx.addInitScript(p => { for (const [k, v] of Object.entries(p)) localStorage.setItem(k, v); }, prefs);
  const page = await ctx.newPage();
  page.on('pageerror', e => problems.push(`${name}: ${e.message}`));
  page.on('response', r => { if (r.status() >= 400 && r.status() !== 401) problems.push(`${name}: HTTP ${r.status()} ${r.url()}`); });
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) problems.push(`${name}: ${m.text()}`); });
  await page.goto(BASE + path, {waitUntil: 'networkidle'});
  if (after) await after(page);
  await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 1) problems.push(`${name}: horizontal overflow ${overflow}px`);
  const dir = await page.evaluate(() => document.documentElement.dir);
  await page.screenshot({path: `screens/${name}.png`, fullPage: true});
  console.log(`${name}: dir=${dir} overflow=${overflow}`);
  await ctx.close();
}

const desktop = {viewport: {width: 1280, height: 860}};
const mobile = {viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true};
await shot(desktop, {'flowly-language': 'en'}, '/account/#login', 'portal-login-en');
await shot(desktop, {'flowly-language': 'ar'}, '/account/#login', 'portal-login-ar');
await shot(desktop, {'flowly-language': 'en', 'flowly-theme': 'dark'}, '/account/#register', 'portal-register-dark');
await shot(mobile, {'flowly-language': 'ar'}, '/account/#register', 'portal-register-ar-mobile');

const signIn = async page => {
  await page.locator('#email').fill(process.env.ADMIN_EMAIL);
  await page.locator('#password').fill(process.env.ADMIN_PASSWORD);
  await page.locator('button[type=submit]').click();
  await page.waitForSelector('.stats', {timeout: 15000});
};
await shot(desktop, {'flowly-language': 'en'}, '/account/#login', 'portal-dashboard-en', signIn);
await shot(mobile, {'flowly-language': 'ar'}, '/account/#login', 'portal-dashboard-ar-mobile', signIn);

const adminLogin = async page => {
  await page.locator('input[name=username]').fill(process.env.ADMIN_EMAIL);
  await page.locator('input[name=password]').fill(process.env.ADMIN_PASSWORD);
  await page.locator('button[type=submit]').click();
  await page.waitForSelector('text=Requests per week', {timeout: 15000});
};
await shot({viewport: {width: 1440, height: 900}}, {}, '/admin/login/?next=/admin/', 'admin-dashboard', adminLogin);

await browser.close();
console.log(problems.length ? 'PROBLEMS:\n  ' + problems.join('\n  ') : 'no console errors, no overflow');
process.exit(problems.length ? 1 : 0);
