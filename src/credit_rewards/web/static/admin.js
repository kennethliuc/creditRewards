(function () {
  const $ = (id) => document.getElementById(id);

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function showLogin() {
    $('loginPanel').classList.remove('hidden');
    $('dashboardPanel').classList.add('hidden');
  }

  function showDashboard() {
    $('loginPanel').classList.add('hidden');
    $('dashboardPanel').classList.remove('hidden');
  }

  async function loadSummary() {
    const res = await fetch('/api/admin/analytics/summary?days=7', { credentials: 'include' });
    if (res.status === 401) {
      return false;
    }
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to load');
    const data = await res.json();
    $('generatedAt').textContent = `Updated ${data.generated_at} · window ${data.window_days}d`;

    const c = data.counts || {};
    $('statsGrid').innerHTML = [
      ['Devices (total)', c.devices_total],
      ['Devices (active)', c.devices_active],
      ['Sessions (7d)', c.sessions_recent],
      ['Events (7d)', c.events_recent],
    ]
      .map(
        ([label, val]) =>
          `<div class="stat-card"><strong>${esc(val ?? 0)}</strong><span>${esc(label)}</span></div>`,
      )
      .join('');

    const byType = data.events_by_type || [];
    $('eventsByType').innerHTML =
      '<tr><th>Event</th><th>Count</th></tr>' +
      byType
        .map((r) => `<tr><td>${esc(r.event_type)}</td><td>${esc(r.count)}</td></tr>`)
        .join('');

    const devices = data.recent_devices || [];
    $('devicesTable').innerHTML =
      '<tr><th>Device</th><th>Cards</th><th>Locale</th><th>Last seen</th></tr>' +
      devices
        .map(
          (d) =>
            `<tr><td class="mono">${esc(d.device_id)}</td><td>${esc(d.card_count ?? '—')}</td><td>${esc(d.locale || '—')}</td><td>${esc(d.last_seen_at)}</td></tr>`,
        )
        .join('');

    const events = data.recent_events || [];
    $('eventsTable').innerHTML =
      '<tr><th>Time</th><th>Event</th><th>Device</th><th>Details</th></tr>' +
      events
        .map((e) => {
          const props = JSON.stringify(e.properties || {});
          return `<tr><td>${esc(e.occurred_at)}</td><td><span class="pill">${esc(e.event_type)}</span></td><td class="mono">${esc((e.device_id || '').slice(0, 8))}…</td><td class="mono">${esc(props.slice(0, 120))}${props.length > 120 ? '…' : ''}</td></tr>`;
        })
        .join('');
    return true;
  }

  $('adminLoginBtn').addEventListener('click', async () => {
    $('loginError').classList.remove('show');
    const password = $('adminPassword').value;
    const res = await fetch('/api/admin/analytics/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      $('loginError').textContent = data.detail || 'Login failed';
      $('loginError').classList.add('show');
      return;
    }
    showDashboard();
    await loadSummary();
  });

  $('adminLogoutBtn').addEventListener('click', async () => {
    await fetch('/api/admin/analytics/logout', { method: 'POST', credentials: 'include' });
    showLogin();
  });

  $('adminRefreshBtn').addEventListener('click', () => loadSummary().catch((e) => alert(e.message)));

  loadSummary()
    .then((ok) => (ok ? showDashboard() : showLogin()))
    .catch((err) => {
      $('loginError').textContent = err.message || 'Failed to load dashboard';
      $('loginError').classList.add('show');
      showLogin();
    });
})();
