/**
 * Trial analytics — anonymous device_id, batched events to /api/analytics/events.
 */
(function () {
  const DEVICE_KEY = 'paycue_device_id';
  const SESSION_KEY = 'paycue_session_id';
  const QUEUE_KEY = 'paycue_analytics_queue';
  const FLUSH_MS = 4000;
  const MAX_QUEUE = 80;

  let enabled = true;
  let queue = [];
  let flushTimer = null;
  let sessionStartedAt = Date.now();

  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function deviceId() {
    try {
      let id = localStorage.getItem(DEVICE_KEY);
      if (!id) {
        id = uuid();
        localStorage.setItem(DEVICE_KEY, id);
      }
      return id;
    } catch (_) {
      return 'anon-' + uuid();
    }
  }

  function sessionId() {
    try {
      let id = sessionStorage.getItem(SESSION_KEY);
      if (!id) {
        id = uuid();
        sessionStorage.setItem(SESSION_KEY, id);
      }
      return id;
    } catch (_) {
      return 'sess-' + uuid();
    }
  }

  function persistQueue() {
    try {
      localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.slice(-MAX_QUEUE)));
    } catch (_) {}
  }

  function restoreQueue() {
    try {
      const raw = localStorage.getItem(QUEUE_KEY);
      if (raw) queue = JSON.parse(raw) || [];
    } catch (_) {
      queue = [];
    }
  }

  function cardCount() {
    try {
      const raw = localStorage.getItem('paycue_wallet_v1');
      if (!raw) return 0;
      const data = JSON.parse(raw);
      return (data.cards || []).length;
    } catch (_) {
      return 0;
    }
  }

  function locale() {
    try {
      return localStorage.getItem('paycue_locale') || navigator.language || '';
    } catch (_) {
      return navigator.language || '';
    }
  }

  function scheduleFlush() {
    if (flushTimer) return;
    flushTimer = setTimeout(() => {
      flushTimer = null;
      flush();
    }, FLUSH_MS);
  }

  async function flush() {
    if (!enabled || !queue.length) return;
    const batch = queue.splice(0, 50);
    persistQueue();
    const body = {
      device_id: deviceId(),
      session_id: sessionId(),
      locale: locale(),
      user_agent: navigator.userAgent || '',
      card_count: cardCount(),
      events: batch,
    };
    try {
      const res = await fetch('/api/analytics/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(body),
        keepalive: true,
      });
      if (res.ok) {
        persistQueue();
        return;
      }
    } catch (_) {}
    queue = batch.concat(queue).slice(-MAX_QUEUE);
    persistQueue();
  }

  function track(eventType, properties) {
    if (!enabled || !eventType) return;
    queue.push({
      event_type: eventType,
      occurred_at: new Date().toISOString(),
      properties: properties || {},
    });
    if (queue.length >= 15) flush();
    else scheduleFlush();
    persistQueue();
  }

  function trackScreen(view) {
    track('screen_view', { view });
  }

  async function init() {
    restoreQueue();
    try {
      const res = await fetch('/api/analytics/status');
      const data = await res.json();
      enabled = !!data.enabled;
    } catch (_) {
      enabled = true;
    }
    if (!enabled) return;

    track('app_open', {
      path: location.pathname,
      referrer: document.referrer || '',
      standalone: !!(navigator.standalone || window.matchMedia('(display-mode: standalone)').matches),
    });

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        track('app_background', {
          duration_sec: Math.round((Date.now() - sessionStartedAt) / 1000),
        });
        flush();
      } else {
        sessionStartedAt = Date.now();
        track('app_foreground', {});
      }
    });

    window.addEventListener('pagehide', () => {
      track('app_close', {
        duration_sec: Math.round((Date.now() - sessionStartedAt) / 1000),
      });
      const body = JSON.stringify({
        device_id: deviceId(),
        session_id: sessionId(),
        locale: locale(),
        user_agent: navigator.userAgent || '',
        card_count: cardCount(),
        events: queue,
      });
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/analytics/events', new Blob([body], { type: 'application/json' }));
        queue = [];
        persistQueue();
      } else {
        flush();
      }
    });
  }

  window.CR_ANALYTICS = { track, trackScreen, flush, deviceId, init };
  init();
})();
