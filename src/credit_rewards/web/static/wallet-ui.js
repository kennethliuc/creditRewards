(() => {
  const STORAGE_KEY = 'creditrewards_wallet_v1';
  const views = ['welcome', 'local-setup', 'register', 'login', 'pay', 'manage'];

  let catalog = [];
  let walletState = null; // { mode: 'local'|'account', email?, cards: [] }
  let activeTab = 'url';
  let pendingAmount = 0;
  let selectedPick = null;
  let selectAllOnNextFocus = false;
  let manageDraft = [];
  let userLocation = null; // { lat, lng } | null
  let merchantConfig = { googlePlacesEnabled: false, locationRecommended: false };

  const $ = (id) => document.getElementById(id);

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function showView(name) {
    views.forEach((v) => {
      const el = $('view-' + v);
      if (el) el.classList.toggle('hidden', v !== name);
    });
  }

  function loadLocalWallet() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function saveLocalWallet(cards) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode: 'local', cards }));
  }

  function clearLocalWallet() {
    localStorage.removeItem(STORAGE_KEY);
  }

  async function fetchAccountSession() {
    const res = await fetch('/api/auth/me', { credentials: 'include' });
    if (!res.ok) return null;
    const data = await res.json();
    return data.authenticated ? data : null;
  }

  async function resolveWallet() {
    const account = await fetchAccountSession();
    if (account?.cards?.length) {
      walletState = { mode: 'account', email: account.email, cards: account.cards };
      return walletState;
    }
    const local = loadLocalWallet();
    if (local?.cards?.length) {
      walletState = { mode: 'local', cards: local.cards };
      return walletState;
    }
    walletState = null;
    return null;
  }

  function walletCardKeys() {
    return (walletState?.cards || []).map((c) => c.card_key);
  }

  function requestUserLocation() {
    return new Promise((resolve) => {
      if (!navigator.geolocation) {
        resolve(null);
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          updateLocationStatus();
          resolve(userLocation);
        },
        () => resolve(null),
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
      );
    });
  }

  function updateLocationStatus() {
    const el = $('locationStatus');
    if (!el) return;
    if (activeTab === 'url') {
      el.textContent = '网站模式：按网购 reward 分类（未知网址默认 Online Shopping）';
      el.className = 'hints location-ok';
      return;
    }
    if (userLocation) {
      el.textContent = '实体店模式：已通过 Google Maps 匹配附近门店';
      el.className = 'hints location-ok';
      return;
    }
    el.textContent = '实体店模式：请允许定位，以便匹配附近门店';
    el.className = 'hints location-warn';
  }

  function purchaseChannelForTab() {
    return activeTab === 'url' ? 'online' : 'in_store';
  }

  function attachLocationToBody(body) {
    body.purchase_channel = purchaseChannelForTab();
    if (activeTab === 'url') {
      return body;
    }
    if (userLocation) {
      body.latitude = userLocation.lat;
      body.longitude = userLocation.lng;
    }
    return body;
  }

  function walletSummaryLabel() {
    const n = walletState?.cards?.length || 0;
    if (walletState?.mode === 'account') {
      return `${walletState.email} · ${n} 张卡`;
    }
    return `本机 · ${n} 张卡`;
  }

  function updateWalletBar() {
    $('walletSummary').textContent = walletSummaryLabel();
  }

  async function loadCatalog() {
    const res = await fetch('/api/cards');
    const data = await res.json();
    catalog = data.cards || [];
    $('paySub').textContent =
      `输入店家和金额，在你钱包的 ${walletState?.cards?.length || 0} 张卡里找出 reward 价值最高的一张。`;
  }

  function renderCardPicker(containerId, { showDetails = false, preselected = [] } = {}) {
    const container = $(containerId);
    const selected = new Set(preselected.map((c) => c.card_key));
    const detailMap = Object.fromEntries(preselected.map((c) => [c.card_key, c]));

    container.innerHTML = catalog
      .map((c) => {
        const checked = selected.has(c.card_key) ? 'checked' : '';
        const det = detailMap[c.card_key] || {};
        const detailBlock = showDetails
          ? `<div class="card-detail-fields" data-detail-for="${esc(c.card_key)}" style="${checked ? '' : 'display:none'}">
              <input type="text" class="nick" placeholder="昵称 (可选)" value="${esc(det.nickname || '')}" maxlength="40" />
              <input type="text" class="last4" placeholder="末四位 (可选)" value="${esc(det.last4 || '')}" maxlength="4" inputmode="numeric" dir="ltr" />
            </div>`
          : '';
        return `<div class="card-pick-row" data-key="${esc(c.card_key)}">
          <label class="card-pick-label">
            <input type="checkbox" class="card-pick-cb" value="${esc(c.card_key)}" ${checked} />
            <span><strong>${esc(c.card_name)}</strong><br><span class="muted">${esc(c.issuer)}</span></span>
          </label>${detailBlock}
        </div>`;
      })
      .join('');

    if (showDetails) {
      container.querySelectorAll('.card-pick-cb').forEach((cb) => {
        cb.addEventListener('change', () => {
          const row = container.querySelector(`[data-detail-for="${cb.value}"]`);
          if (row) row.style.display = cb.checked ? '' : 'none';
        });
      });
    }
  }

  function readPickerCards(containerId, withDetails) {
    const container = $(containerId);
    const cards = [];
    container.querySelectorAll('.card-pick-cb:checked').forEach((cb) => {
      const key = cb.value;
      const meta = catalog.find((c) => c.card_key === key) || {};
      const card = {
        card_key: key,
        card_name: meta.card_name || key,
        nickname: '',
        last4: '',
      };
      if (withDetails) {
        const fields = container.querySelector(`[data-detail-for="${key}"]`);
        if (fields) {
          card.nickname = fields.querySelector('.nick')?.value.trim() || '';
          card.last4 = (fields.querySelector('.last4')?.value || '').replace(/\D/g, '').slice(0, 4);
        }
      }
      cards.push(card);
    });
    return cards;
  }

  function activeInputEl() {
    return activeTab === 'url' ? $('merchantUrl') : $('merchantName');
  }

  function markInputsForReentry() {
    selectAllOnNextFocus = true;
  }

  function renderMerchantHints(items) {
    $('merchant-name-hints').innerHTML = (items || [])
      .map((m) => {
        const cat = m.category || m.inStoreCategory || '';
        return `<option value="${esc(m.name)}">${esc(cat)}</option>`;
      })
      .join('');
  }

  let suggestTimer = null;
  async function refreshMerchantHints(query) {
    const q = (query || '').trim();
    const channel = purchaseChannelForTab();
    const url =
      q.length >= 2
        ? `/api/merchants?q=${encodeURIComponent(q)}&purchase_channel=${encodeURIComponent(channel)}`
        : '/api/merchants';
    try {
      const res = await fetch(url);
      const data = await res.json();
      renderMerchantHints(q.length >= 2 ? data.suggestions || [] : data.merchants || []);
    } catch (_) {}
  }

  function bindReentryInput(el) {
    el.addEventListener('focus', () => {
      if (!selectAllOnNextFocus) return;
      selectAllOnNextFocus = false;
      requestAnimationFrame(() => {
        if (document.activeElement === el) el.select();
      });
    });
    el.addEventListener('beforeinput', (e) => {
      if (e.inputType !== 'insertText' && e.inputType !== 'insertCompositionText') return;
      if (el.selectionStart !== 0 || el.selectionEnd !== 0 || !el.value.length) return;
      e.preventDefault();
      const text = e.data || '';
      const end = el.value.length;
      el.setSelectionRange(end, end);
      el.setRangeText(text, end, end, 'end');
    });
  }

  function confidenceLabel(c) {
    if (c === 'high') return '<span class="confidence-high">高置信度</span>';
    if (c === 'medium') return '<span class="confidence-medium">中置信度 — 请核对</span>';
    return '<span class="confidence-low">低置信度 — 请仔细核对</span>';
  }

  function showConfirmModal(data) {
    activeInputEl().blur();
    const best = data.best;
    selectedPick = best;

    $('confirmMerchant').textContent = best.merchantName;
    $('confirmCategory').textContent = `→ ${best.spendBonusCategoryName}${data.purchaseChannel === 'online' ? '（网站）' : data.purchaseChannel === 'in_store' ? '（实体店）' : ''}`;
    const hostLine = data.parsedHost ? `页面 host: ${data.parsedHost} · ` : '';
    const parsedLine = data.parsedStoreName
      ? `从网址解析: ${esc(data.parsedStoreName)}${data.parsedStoreDomain ? ` (${esc(data.parsedStoreDomain)})` : ''} · `
      : '';
    const channelLine = data.purchaseChannel === 'online'
      ? '网站 · '
      : data.purchaseChannel === 'in_store' ? '实体店 · ' : '';
    const sourceLine = best.source === 'nominatim' ? ' · OpenStreetMap 推断'
      : best.source === 'google_places' ? ' · Google Maps 门店'
      : best.source === 'url_parse' ? ' · 官网网购推断' : '';
    $('confirmMeta').innerHTML =
      `${channelLine}${parsedLine}匹配: ${esc(best.matchedOn)} (${esc(best.matchType)}) · ${confidenceLabel(best.confidence)}${sourceLine}`;

    const candidates = (data.candidates || []).filter((c) => c.merchantId !== best.merchantId);
    const block = $('candidateBlock');
    const list = $('candidateList');
    if (candidates.length) {
      block.style.display = 'block';
      list.innerHTML = [best, ...candidates]
        .map(
          (c) => `
        <li>
          <label class="${c.merchantId === selectedPick.merchantId ? 'selected' : ''}">
            <input type="radio" name="merchantPick" value="${esc(c.merchantId)}"
              ${c.merchantId === selectedPick.merchantId ? 'checked' : ''} />
            <span>
              <strong>${esc(c.merchantName)}</strong> → ${esc(c.spendBonusCategoryName)}
                <br><span style="color:var(--muted);font-size:.78rem">${esc(c.matchType)} · ${esc(c.confidence)}${c.source === 'nominatim' ? ' · OSM' : ''}${c.source === 'google_places' ? ' · Google Maps' : ''}</span>
            </span>
          </label>
        </li>`
        )
        .join('');
      list.querySelectorAll('input[name=merchantPick]').forEach((radio) => {
        radio.addEventListener('change', () => {
          const all = [best, ...candidates];
          selectedPick = all.find((c) => c.merchantId === radio.value) || best;
          list.querySelectorAll('label').forEach((l) => l.classList.remove('selected'));
          radio.closest('label').classList.add('selected');
          $('confirmMerchant').textContent = selectedPick.merchantName;
          $('confirmCategory').textContent = `→ ${selectedPick.spendBonusCategoryName}${data.purchaseChannel === 'online' ? '（网站）' : data.purchaseChannel === 'in_store' ? '（实体店）' : ''}`;
        });
      });
    } else {
      block.style.display = 'none';
      list.innerHTML = '';
    }
    $('confirmModal').classList.add('show');
  }

  function hideConfirmModal(refocusInput = false) {
    $('confirmModal').classList.remove('show');
    if (!refocusInput) return;
    const input = activeInputEl();
    input.focus({ preventScroll: true });
    requestAnimationFrame(() => {
      if (document.activeElement === input) input.select();
    });
  }

  async function runRecommend(pick, amount_usd) {
    const errorEl = $('error');
    const resultEl = $('result');
    errorEl.classList.remove('show');
    resultEl.classList.remove('show');

    const keys = walletCardKeys();
    if (!keys.length) {
      throw new Error('请先添加至少一张卡');
    }

    const payload = {
      merchant_id: pick.merchantId,
      merchant_name: pick.merchantName,
      amount_usd,
      card_keys: keys,
      category: pick.spendBonusCategoryName,
      purchase_channel: purchaseChannelForTab(),
    };

    const res = await fetch('/api/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Request failed');

    const best = data.best;
    const merchant = data.merchant || {};
    $('bestName').textContent = best.card_name;
    $('bestValue').textContent = `≈ $${best.estimated_value_usd.toFixed(2)} reward 价值`;
    const storeLine = merchant.merchantName
      ? `${merchant.merchantName} → ${data.resolved_category}`
      : data.resolved_category;
    $('bestMeta').textContent =
      `$${amount_usd.toFixed(2)} · ${storeLine} · ${best.multiplier}x · ${best.reason}`;
    $('rankHead').textContent = `钱包 ${data.card_count} 张卡排名（official CPP）`;
    $('rankings').innerHTML = data.rankings
      .map(
        (r) => `
        <div class="rank-row ${r.rank === 1 ? 'top' : ''}">
          <div class="rank-num">#${r.rank}</div>
          <div>
            <div class="rank-name">${esc(r.card_name)}</div>
            <div class="rank-sub">${r.multiplier}x · ${esc(r.reason)}</div>
          </div>
          <div class="rank-usd">$${r.estimated_value_usd.toFixed(2)}</div>
        </div>`
      )
      .join('');
    resultEl.classList.add('show');
    resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    markInputsForReentry();
  }

  function renderManageList() {
    const list = $('manageCardList');
    list.innerHTML = manageDraft
      .map(
        (c, i) => `
      <div class="manage-row" data-idx="${i}">
        <div class="manage-row-head"><strong>${esc(c.card_name || c.card_key)}</strong>
          <button type="button" class="link-btn remove-card" data-idx="${i}">移除</button></div>
      </div>`
      )
      .join('');
    list.querySelectorAll('.remove-card').forEach((btn) => {
      btn.addEventListener('click', async () => {
        $('manageError').classList.remove('show');
        if (manageDraft.length <= 1) {
          $('manageError').textContent = '至少保留一张卡';
          $('manageError').classList.add('show');
          return;
        }
        manageDraft.splice(Number(btn.dataset.idx), 1);
        try {
          await persistManageDraft();
          renderManageList();
          renderAddCardSelect();
        } catch (err) {
          $('manageError').textContent = err.message;
          $('manageError').classList.add('show');
        }
      });
    });
  }

  function renderAddCardSelect() {
    const sel = $('addCardSelect');
    const inWallet = new Set(manageDraft.map((c) => c.card_key));
    const available = catalog.filter((c) => !inWallet.has(c.card_key));
    sel.innerHTML =
      '<option value="">— 添加一张卡 —</option>' +
      available.map((c) => `<option value="${esc(c.card_key)}">${esc(c.card_name)} (${esc(c.issuer)})</option>`).join('');
  }

  async function persistManageDraft() {
    if (!manageDraft.length) throw new Error('至少保留一张卡');

    if (walletState?.mode === 'account') {
      const res = await fetch('/api/wallet', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ cards: manageDraft }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Save failed');
      walletState.cards = data.cards;
      manageDraft = walletState.cards.map((c) => ({ ...c }));
    } else {
      saveLocalWallet(manageDraft);
      walletState = { mode: 'local', cards: manageDraft.map((c) => ({ ...c })) };
    }
    updateWalletBar();
    await loadCatalog();
  }

  async function enterPayFlow() {
    await loadCatalog();
    updateWalletBar();
    showView('pay');
    if (activeTab === 'name' && !userLocation) {
      await requestUserLocation();
    }
    updateLocationStatus();
  }

  async function init() {
    bindReentryInput($('merchantUrl'));
    bindReentryInput($('merchantName'));
    $('merchantName').addEventListener('input', () => {
      clearTimeout(suggestTimer);
      suggestTimer = setTimeout(() => refreshMerchantHints($('merchantName').value), 200);
    });
    bindReentryInput($('amount'));

    document.querySelectorAll('.tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeTab = btn.dataset.tab;
        document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === activeTab));
        $('panel-url').classList.toggle('active', activeTab === 'url');
        $('panel-name').classList.toggle('active', activeTab === 'name');
        updateLocationStatus();
      });
    });

    $('btnLocal').addEventListener('click', async () => {
      if (!catalog.length) await loadCatalog();
      renderCardPicker('localCardPicker', { showDetails: false });
      showView('local-setup');
    });
    $('localBack').addEventListener('click', () => showView('welcome'));
    $('btnRegister').addEventListener('click', async () => {
      if (!catalog.length) await loadCatalog();
      renderCardPicker('registerCardPicker', { showDetails: true });
      showView('register');
    });
    $('btnLogin').addEventListener('click', () => showView('login'));

    $('localSave').addEventListener('click', () => {
      const cards = readPickerCards('localCardPicker', false);
      if (!cards.length) {
        $('localSetupError').textContent = '请至少选择一张卡';
        $('localSetupError').classList.add('show');
        return;
      }
      saveLocalWallet(cards);
      walletState = { mode: 'local', cards };
      $('localSetupError').classList.remove('show');
      enterPayFlow();
    });

    $('registerSubmit').addEventListener('click', async () => {
      $('registerError').classList.remove('show');
      const email = $('regEmail').value.trim();
      const password = $('regPassword').value;
      const cards = readPickerCards('registerCardPicker', true);
      if (!cards.length) {
        $('registerError').textContent = '请至少选择一张卡';
        $('registerError').classList.add('show');
        return;
      }
      try {
        const res = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ email, password, cards }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Register failed');
        walletState = { mode: 'account', email: data.email, cards: data.cards };
        enterPayFlow();
      } catch (err) {
        $('registerError').textContent = err.message;
        $('registerError').classList.add('show');
      }
    });

    $('loginSubmit').addEventListener('click', async () => {
      $('loginError').classList.remove('show');
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            email: $('loginEmail').value.trim(),
            password: $('loginPassword').value,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Login failed');
        walletState = { mode: 'account', email: data.email, cards: data.cards };
        if (!data.cards?.length) {
          renderCardPicker('registerCardPicker', { showDetails: true, preselected: [] });
          showView('register');
          return;
        }
        enterPayFlow();
      } catch (err) {
        $('loginError').textContent = err.message;
        $('loginError').classList.add('show');
      }
    });

    $('btnManage').addEventListener('click', () => {
      manageDraft = (walletState?.cards || []).map((c) => ({ ...c }));
      renderManageList();
      renderAddCardSelect();
      $('manageError').classList.remove('show');
      $('manageAccountActions').style.display = walletState?.mode === 'account' ? 'block' : 'none';
      $('manageLocalActions').style.display = walletState?.mode === 'local' ? 'block' : 'none';
      showView('manage');
    });

    $('manageBack').addEventListener('click', () => showView('pay'));

    $('addCardBtn').addEventListener('click', async () => {
      const key = $('addCardSelect').value;
      if (!key) return;
      $('manageError').classList.remove('show');
      const meta = catalog.find((c) => c.card_key === key);
      manageDraft.push({
        card_key: key,
        card_name: meta?.card_name || key,
        nickname: '',
        last4: '',
      });
      try {
        await persistManageDraft();
        renderManageList();
        renderAddCardSelect();
      } catch (err) {
        manageDraft.pop();
        $('manageError').textContent = err.message;
        $('manageError').classList.add('show');
      }
    });

    $('btnLogout').addEventListener('click', async () => {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
      walletState = null;
      showView('welcome');
    });

    $('btnResetLocal').addEventListener('click', () => {
      clearLocalWallet();
      walletState = null;
      showView('welcome');
    });

    $('form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const errorEl = $('error');
      const go = $('go');
      errorEl.classList.remove('show');
      $('result').classList.remove('show');
      go.disabled = true;
      pendingAmount = parseFloat($('amount').value);
      const body = {};
      if (activeTab === 'url') {
        const url = $('merchantUrl').value.trim();
        if (!url) {
          errorEl.textContent = '请粘贴结账页 URL';
          errorEl.classList.add('show');
          go.disabled = false;
          return;
        }
        body.merchant_url = url;
      } else {
        const name = $('merchantName').value.trim();
        if (!name) {
          errorEl.textContent = '请输入店名';
          errorEl.classList.add('show');
          go.disabled = false;
          return;
        }
        body.merchant_name = name;
      }
      try {
        if (activeTab === 'name' && !userLocation) {
          await requestUserLocation();
        }
        const res = await fetch('/api/merchant/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(attachLocationToBody(body)),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Request failed');
        if (data.needsConfirmation || activeTab === 'url') showConfirmModal(data);
        else await runRecommend(data.best, pendingAmount);
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.add('show');
      } finally {
        go.disabled = false;
        markInputsForReentry();
      }
    });

    $('confirmGo').addEventListener('click', async () => {
      const btn = $('confirmGo');
      btn.disabled = true;
      try {
        hideConfirmModal();
        await runRecommend(selectedPick, pendingAmount);
      } catch (err) {
        $('error').textContent = err.message;
        $('error').classList.add('show');
      } finally {
        btn.disabled = false;
      }
    });

    $('confirmCancel').addEventListener('click', () => {
      markInputsForReentry();
      hideConfirmModal(true);
    });
    $('confirmModal').addEventListener('click', (e) => {
      if (e.target.id === 'confirmModal') {
        markInputsForReentry();
        hideConfirmModal(true);
      }
    });

    try {
      const cfgRes = await fetch('/api/merchant/config');
      if (cfgRes.ok) merchantConfig = await cfgRes.json();
    } catch (_) {}

    await refreshMerchantHints('');

    await loadCatalog();
    const w = await resolveWallet();
    if (w) enterPayFlow();
    else showView('welcome');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
