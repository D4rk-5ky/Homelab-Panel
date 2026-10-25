/* Shared fragments contain only escaped device data, never session content. */
(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('dashboard-config').textContent);
  const statusCards = new Map(Array.from(document.querySelectorAll('[data-device-status]'),
    (node) => [node.dataset.deviceStatus, node]));
  const jobLists = new Map(Array.from(document.querySelectorAll('.job-list'),
    (node) => [node.dataset.deviceId, node]));
  const connection = document.getElementById('dashboard-connection');
  const messages = document.getElementById('action-messages');
  const pendingActions = new Set();
  let revision = config.revision;
  let instance = config.instance;
  let timer;
  let inFlight = null;
  let refreshRequested = false;
  const moreButtons = new Map(Array.from(document.querySelectorAll('[data-jobs-more]'),
    (node) => [node.dataset.jobsMore, node]));
  const pendingLoads = new Map();
  let activeLoad = null;
  let clockTimer;
  let clockEpoch = config.serverEpoch * 1000;
  let clockStarted = performance.now();

  function updateClocks() {
    if (document.hidden) return;
    // Use server time + monotonic elapsed time, independent of the browser's wall clock.
    const now = (clockEpoch + performance.now() - clockStarted) / 1000;
    document.querySelectorAll('[data-panel-age]').forEach((node) => {
      node.textContent = Math.max(0, Math.floor(now - Number(node.dataset.panelAge)));
    });
    document.querySelectorAll('[data-panel-countdown]').forEach((node) => {
      node.textContent = Math.max(0, Math.ceil(Number(node.dataset.panelCountdown) - now));
    });
  }

  function syncClock(epoch) {
    clockEpoch = epoch * 1000;
    clockStarted = performance.now();
    updateClocks();
  }

  function updateMoreButton(deviceId) {
    const list = jobLists.get(deviceId);
    const button = moreButtons.get(deviceId);
    if (!button) return;
    button.hidden = Number(list.dataset.jobsLimit) >= Number(list.dataset.jobsTotal);
    button.disabled = pendingLoads.has(deviceId) || activeLoad === deviceId;
  }

  function requestMoreJobs(deviceId) {
    const list = jobLists.get(deviceId);
    if (!list || pendingLoads.has(deviceId) || activeLoad === deviceId) return;
    const limit = Number(list.dataset.jobsLimit);
    const total = Number(list.dataset.jobsTotal);
    if (limit >= total) return;
    pendingLoads.set(deviceId, Math.min(total, limit + config.jobPageSize));
    updateMoreButton(deviceId);
    poll();
  }

  function applyFragments(data) {
    for (const [deviceId, fragments] of Object.entries(data.devices)) {
      if (fragments.status !== undefined && statusCards.has(deviceId)) {
        updateStatus(statusCards.get(deviceId), fragments.status);
      }
      if (fragments.jobs !== undefined && jobLists.has(deviceId)) {
        const list = jobLists.get(deviceId);
        list.dataset.jobsLimit = fragments.jobs_limit;
        list.dataset.jobsTotal = fragments.jobs_total;
        updateJobs(list, fragments.jobs);
        updateMoreButton(deviceId);
      }
    }
    syncClock(data.server_epoch);
  }

  function fitFiveJobs(list) {
    const jobs = list.querySelectorAll('.job');
    list.style.maxHeight = jobs.length >= 5
      ? `${Math.ceil(jobs[4].getBoundingClientRect().bottom - jobs[0].getBoundingClientRect().top)}px`
      : '';
  }

  function updateJobs(list, html) {
    const oldTop = list.scrollTop;
    const listTop = list.getBoundingClientRect().top;
    const anchor = Array.from(list.querySelectorAll('.job'))
      .find((job) => job.getBoundingClientRect().bottom > listTop);
    const anchorId = anchor?.dataset.jobId;
    const offset = anchor ? anchor.getBoundingClientRect().top - listTop : 0;
    list.dataset.updating = "true";
    list.innerHTML = html;
    fitFiveJobs(list);
    // Readers scrolling through history keep their place when new jobs arrive.
    const replacement = oldTop > 0 && Array.from(list.querySelectorAll('.job'))
      .find((job) => job.dataset.jobId === anchorId);
    list.scrollTop = replacement
      ? list.scrollTop + replacement.getBoundingClientRect().top - listTop - offset
      : oldTop;
    requestAnimationFrame(() => { delete list.dataset.updating; });
  }

  function updateStatus(card, html) {
    const focusedAction = card.contains(document.activeElement) && document.activeElement.form?.action;
    card.innerHTML = html;
    card.querySelectorAll('form[data-panel-action]').forEach((form) => {
      form.querySelectorAll('button').forEach((button) => {
        button.disabled = pendingActions.has(form.action);
        if (focusedAction === form.action) button.focus({ preventScroll: true });
      });
    });
  }

  function loginRequired(response, data) {
    if (response.status !== 401) return false;
    window.location.assign(data.login_url || config.loginUrl);
    return true;
  }

  async function poll() {
    clearTimeout(timer);
    if (document.hidden) return;
    if (inFlight) {
      refreshRequested = true;
      return inFlight;
    }
    inFlight = (async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        activeLoad = pendingLoads.size ? pendingLoads.keys().next().value : null;
        const target = activeLoad ? jobLists.get(activeLoad).dataset.jobsUrl : config.url;
        const url = new URL(target, window.location.href);
        if (activeLoad) {
          url.searchParams.set('limit', pendingLoads.get(activeLoad));
          pendingLoads.delete(activeLoad);
        } else {
          url.searchParams.set('since', revision);
          url.searchParams.set('instance', instance);
          url.searchParams.set('jobs', JSON.stringify(Object.fromEntries(
            Array.from(jobLists, ([id, list]) => [id, Number(list.dataset.jobsLimit)]))));
        }
        const response = await fetch(url, {
          headers: { Accept: 'application/json' }, credentials: 'same-origin',
          cache: 'no-store', signal: controller.signal,
        });
        const data = await response.json();
        if (loginRequired(response, data)) return;
        if (!response.ok) throw new Error('Status request failed');
        applyFragments(data);
        if (activeLoad) {
          // This response covers one device only. Keep the global cursor until a full poll.
          refreshRequested = true;
        } else {
          revision = data.revision;
          instance = data.instance;
        }
        document.getElementById('dashboard-updated-at').textContent = data.updated_at;
        connection.hidden = true;
      } catch (_) {
        connection.textContent = 'Forbindelsen til panelet er afbrudt. Viste data opdateres ikke. Prøver igen automatisk.';
        connection.hidden = false;
      } finally {
        clearTimeout(timeout);
        const finishedLoad = activeLoad;
        activeLoad = null;
        if (finishedLoad) updateMoreButton(finishedLoad);
      }
    })();
    try {
      await inFlight;
    } finally {
      inFlight = null;
      const delay = refreshRequested || pendingLoads.size ? 0 : config.refreshMilliseconds;
      refreshRequested = false;
      if (!document.hidden) timer = setTimeout(poll, delay);
    }
  }

  function showMessage(ok, message) {
    const node = document.createElement('div');
    node.className = `flash ${ok ? 'success' : 'error'}`;
    node.textContent = message;
    messages.replaceChildren(node);
  }

  document.addEventListener('submit', async (event) => {
    const form = event.target;
    // Inline confirmation handlers run first; cancelled prompts send nothing.
    if (event.defaultPrevented || !form.matches('form[data-panel-action]')) return;
    event.preventDefault();
    if (pendingActions.has(form.action)) return;
    pendingActions.add(form.action);
    form.querySelectorAll('button').forEach((button) => { button.disabled = true; });
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: new FormData(form),
        headers: { Accept: 'application/json' }, credentials: 'same-origin', cache: 'no-store',
      });
      const data = await response.json();
      if (loginRequired(response, data)) return;
      if (!response.ok) throw new Error('Action response failed');
      showMessage(data.ok, data.message);
      await poll();
    } catch (_) {
      // Never retry a power action automatically: it may already have executed.
      showMessage(false, 'Kunne ikke hente resultatet. Handlingen kan være sendt; kontrollér jobstatus før du prøver igen.');
    } finally {
      pendingActions.delete(form.action);
      document.querySelectorAll('form[data-panel-action]').forEach((current) => {
        if (current.action === form.action) {
          current.querySelectorAll('button').forEach((button) => { button.disabled = false; });
        }
      });
    }
  });

  moreButtons.forEach((button, id) => {
    button.addEventListener('click', () => requestMoreJobs(id));
    updateMoreButton(id);
  });
  jobLists.forEach((list, deviceId) => {
    const atBottom = () => list.scrollTop + list.clientHeight >= list.scrollHeight - 24;
    list.addEventListener('scroll', () => {
      if (!list.dataset.updating && list.scrollTop > 0 && atBottom()) requestMoreJobs(deviceId);
    }, { passive: true });
    list.addEventListener('wheel', (event) => {
      if (event.deltaY > 0 && atBottom()) requestMoreJobs(deviceId);
    }, { passive: true });
    list.addEventListener('keydown', (event) => {
      if (['ArrowDown', 'PageDown', 'End'].includes(event.key) && atBottom()) requestMoreJobs(deviceId);
    });
    fitFiveJobs(list);
    if ('ResizeObserver' in window) {
      let previousWidth;
      new ResizeObserver(([entry]) => {
        if (entry.contentRect.width === previousWidth) return;
        previousWidth = entry.contentRect.width;
        fitFiveJobs(list);
      }).observe(list);
    } else {
      window.addEventListener('resize', () => fitFiveJobs(list));
    }
  });
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer);
    clearInterval(clockTimer);
    if (!document.hidden) {
      updateClocks();
      clockTimer = setInterval(updateClocks, 1000);
      poll();
    }
  });
  updateClocks();
  if (!document.hidden) clockTimer = setInterval(updateClocks, 1000);
  timer = setTimeout(poll, config.refreshMilliseconds);
})();
