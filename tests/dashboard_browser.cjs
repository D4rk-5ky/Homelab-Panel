/* Optional end-to-end check: requires Playwright + a Chromium install and Python deps.
 * PYTHON=.venv/bin/python node tests/dashboard_browser.cjs
 * CHROMIUM_EXECUTABLE_PATH may select an existing local Chromium binary.
 * All power/MQTT work is mocked; the fixture listens on localhost only.
 */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const path = require('node:path');
const { chromium } = require('playwright');

const fixture = String.raw`
import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, "tests")
from test_home_assistant import load_panel
from flask import request, jsonify
from waitress import create_server
panel = load_panel()
state = tempfile.TemporaryDirectory()
for field, filename in (("PANEL_HISTORY_FILE", "history.json"), ("PANEL_RUNTIME_FILE", "runtime.json"), ("PANEL_JOBS_FILE", "jobs.json")):
    setattr(panel, field, str(Path(state.name) / filename))
panel.WEB_AUTH_CONFIG.update(enabled=True, username="browser", password="browser-test")
panel.app.config.update(SECRET_KEY="browser-test-secret", TESTING=True)
panel.PAGE_REFRESH_SECONDS = 1
for device_id in panel.REMOTE_DEVICES:
    panel.DEVICE_STATUS_CACHE[device_id] = {"ping_ok": True, "cached_at": time.time()}
panel.ping_host = lambda ip: (_ for _ in ()).throw(AssertionError("Web ping"))
def fake_action(device_id, button_id, source):
    panel.update_panel_job(device_id, "browser-command", command=button_id, status="success", message="Mock action finished")
    return True, "Mock action finished"
panel.execute_and_record_remote_action = fake_action
@panel.app.post("/_test/jobs")
def add_jobs():
    for i in range(9):
        panel.update_panel_job("aoostar_wtr", "browser-" + str(i), status="success", label="Job " + str(i),
                               message="<script>window.injected=true</script>\n" + ("Long message " * 10), updated_at="2026-10-24T12:00:0" + str(i))
    return jsonify(ok=True)
@panel.app.post("/_test/change-job")
def change_job():
    panel.update_panel_job("aoostar_wtr", "browser-8", message="Updated job without navigation")
    return jsonify(ok=True)
@panel.app.post("/_test/restart-cache")
def restart_cache():
    panel.DASHBOARD_CACHE = type(panel.DASHBOARD_CACHE)(panel.render_template)
    return jsonify(ok=True)
server = create_server(panel.app, host="127.0.0.1", port=0, threads=4)
print("READY " + str(server.effective_port), flush=True)
server.run()
`;

(async () => {
  const server = spawn(process.env.PYTHON || 'python3', ['-B', '-u', '-c', fixture], {
    cwd: path.resolve(__dirname, '..'), env: process.env, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let browser;
  let stderr = '';
  server.stderr.on('data', (chunk) => { stderr += chunk; });
  try {
    const port = await new Promise((resolve, reject) => {
      let output = '';
      const timeout = setTimeout(() => reject(new Error('Fixture did not start: ' + stderr)), 10000);
      server.stdout.on('data', (chunk) => {
        output += chunk;
        const match = output.match(/READY (\d+)/);
        if (match) { clearTimeout(timeout); resolve(Number(match[1])); }
      });
      server.once('exit', (code) => { clearTimeout(timeout); reject(new Error(`Fixture exited ${code}: ${stderr}`)); });
    });
    const base = `http://127.0.0.1:${port}`;
    browser = await chromium.launch({ headless: true,
      ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}),
      args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    });
    const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(base);
    await page.fill('#username', 'browser');
    await page.fill('#password', 'browser-test');
    await Promise.all([page.waitForURL(base + '/'), page.click('button[type=submit]')]);
    await page.waitForResponse((response) => response.url().includes('/api/dashboard'));
    const poll = await context.request.get(base + '/api/dashboard');
    const snapshot = await poll.json();
    const unchanged = await context.request.get(base + `/api/dashboard?since=${snapshot.revision}&instance=${snapshot.instance}`);
    assert.deepEqual((await unchanged.json()).devices, {});
    let navigations = 0;
    let actionPosts = 0;
    let polls = 0;
    page.on('framenavigated', (frame) => { if (frame === page.mainFrame()) navigations++; });
    page.on('request', (request) => {
      if (request.url().includes('/mqtt/') && request.method() === 'POST') actionPosts++;
      if (request.url().includes('/api/dashboard')) polls++;
    });
    await page.evaluate(() => { window.shellMarker = 'persistent'; });
    await context.request.post(base + '/_test/jobs');
    await page.waitForFunction(() => document.querySelectorAll('[data-device-id="aoostar_wtr"] .job').length === 9);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    const list = page.locator('.job-list[data-device-id="aoostar_wtr"]');
    await list.evaluate((node) => { node.focus(); node.scrollTop = 100; node.testMarker = true; });
    const scroll = await list.evaluate((node) => node.scrollTop);
    await context.request.post(base + '/_test/change-job');
    await page.waitForFunction(() => document.querySelector('[data-device-id="aoostar_wtr"]').textContent.includes('Updated job without navigation'));
    assert.equal(await list.evaluate((node) => node.testMarker), true);
    assert.equal(await list.evaluate((node) => document.activeElement === node), true);
    assert.ok(Math.abs((await list.evaluate((node) => node.scrollTop)) - scroll) < 2);
    const otherTab = await context.newPage();
    await otherTab.goto(base);
    const action = page.locator('form[action="/mqtt/aoostar_wtr/shutdown_delay"] button');
    page.once('dialog', (dialog) => dialog.dismiss());
    await action.click();
    await page.waitForTimeout(200);
    assert.equal(actionPosts, 0, 'Cancelled confirmation must not send a command');
    page.once('dialog', (dialog) => dialog.accept());
    await action.click();
    await page.waitForFunction(() => document.getElementById('action-messages').textContent.includes('MQTT-handling sendt'));
    assert.equal(actionPosts, 1);
    assert.equal(await otherTab.locator('#action-messages').innerText(), '');
    assert.equal(await page.evaluate(() => window.shellMarker), 'persistent');
    assert.equal(navigations, 0, 'Polls and commands must not navigate');
    await page.route('**/api/dashboard*', (route) => route.abort());
    await page.locator('#dashboard-connection').waitFor({ state: 'visible' });
    await page.unroute('**/api/dashboard*');
    await page.locator('#dashboard-connection').waitFor({ state: 'hidden' });
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const beforePause = polls;
    await page.waitForTimeout(1300);
    assert.equal(polls, beforePause, 'Hidden tabs must stop polling');
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForResponse((response) => response.url().includes('/api/dashboard'));
    await context.request.post(base + '/_test/restart-cache');
    await page.waitForResponse(async (response) => {
      if (!response.url().includes('/api/dashboard')) return false;
      return Object.keys((await response.json()).devices).length > 0;
    });
    assert.equal(await page.evaluate(() => window.shellMarker), 'persistent');
    // Mobile wrapping must not cause horizontal overflow or lose the job scroller.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(100);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await context.clearCookies();
    await page.waitForURL(base + '/login');
    assert.deepEqual(errors, []);
    console.log('PASS: real Waitress + Chromium: login, deltas, no reload, escaped jobs, scroll/focus, confirmations, private results, network recovery, hidden-tab pause, restart, mobile, session expiry');
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    if (server.exitCode === null) await once(server, 'exit');
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
