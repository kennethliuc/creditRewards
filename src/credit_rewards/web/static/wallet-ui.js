(() => {
  const STORAGE_KEY = 'paycue_wallet_v1';
  const IMAGE_CACHE_KEY = 'paycue_card_images_v1';
  const PAY_TAB_KEY = 'paycue_pay_tab_v1';
  const LAST_MERCHANT_KEY = 'paycue_last_merchant_v1';
  const DEFAULT_AMOUNT = 100;
  const views = ['language', 'local-setup', 'pay', 'savings-history', 'manage'];
  let languageReturnView = 'bootstrap';
  let savingsReturnView = 'pay';
  let selectedSavingsIds = new Set();

  function t(key, vars) {
    return window.CR_I18N?.t(key, vars) ?? key;
  }

  function applyPageI18n() {
    window.CR_I18N?.apply(document);
    window.CR_PWA?.refreshInstallBanner();
    updateLocationStatus();
    updatePaySub();
    updateWalletNav();
    renderSavingsBanner();
    renderWalletSavingsPanel();
  }

  function updatePaySub() {
    const el = $('paySub');
    if (!el) return;
    el.textContent = t('pay.sub', { count: walletState?.cards?.length || 0 });
    updateWalletNav();
  }

  function updateWalletNav() {
    const label = $('walletNavLabel');
    if (!label) return;
    label.textContent = t('nav.walletBtn', { count: walletState?.cards?.length || 0 });
  }

  function savingsApi() {
    return window.CR_SAVINGS;
  }

  function renderSavingsStatRow(labelKey, bucket) {
    const api = savingsApi();
    if (!api || !bucket.count) return '';
    return `
      <div class="savings-stat">
        <div>
          <div class="savings-stat-label">${esc(t(labelKey))}</div>
          <div class="savings-stat-meta">${esc(t('savings.times', { count: bucket.count }))}</div>
        </div>
        <div class="savings-stat-value">~$${esc(api.formatUsd(bucket.reward_usd))}</div>
      </div>`;
  }

  function formatHistoryDate(ts) {
    const loc =
      window.CR_I18N?.locale === 'zh' ? 'zh-Hans' : window.CR_I18N?.locale === 'es' ? 'es' : 'en';
    return new Date(ts).toLocaleString(loc, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  function historyRowLabel(row, api) {
    const merchant = row.merchant || row.category || '—';
    const parts = [formatHistoryDate(row.ts), merchant];
    if (row.card_name) parts.push(row.card_name);
    if (!row.amount_provided) {
      parts.push(t('savings.historyRowEst', { amount: api.formatUsd(row.purchase_amount_usd) }));
    }
    return parts.join(' · ');
  }

  function updateRemoveSavingsButton() {
    const btn = $('btnRemoveSavingsSelected');
    if (!btn) return;
    btn.disabled = selectedSavingsIds.size === 0;
  }

  function renderSavingsHistory() {
    const api = savingsApi();
    const list = $('savingsHistoryList');
    const empty = $('savingsHistoryEmpty');
    const summary = $('savingsHistorySummary');
    if (!api || !list) return;

    const stats = api.getStats();
    const rows = api.listAll();
    selectedSavingsIds = new Set([...selectedSavingsIds].filter((id) => rows.some((r) => r.id === id)));

    if (summary) {
      summary.innerHTML =
        renderSavingsStatRow('savings.month', stats.month) +
        renderSavingsStatRow('savings.quarter', stats.quarter) +
        renderSavingsStatRow('savings.allTime', stats.allTime);
    }

    if (!rows.length) {
      list.innerHTML = '';
      empty?.classList.remove('hidden');
    } else {
      empty?.classList.add('hidden');
      list.innerHTML = rows
        .map((row) => {
          const checked = selectedSavingsIds.has(row.id);
          return `
        <label class="savings-history-row ${checked ? 'selected' : ''}" data-id="${esc(row.id)}">
          <input type="checkbox" data-id="${esc(row.id)}" ${checked ? 'checked' : ''} />
          <div class="savings-history-main">
            <div class="savings-history-title">${esc(row.merchant || row.category || '—')}</div>
            <div class="savings-history-meta">${esc(historyRowLabel(row, api))}</div>
            <div class="savings-history-reward">${esc(
              t('savings.historyRowReward', { amount: api.formatUsd(row.reward_usd) }),
            )}</div>
          </div>
        </label>`;
        })
        .join('');
    }

    list.querySelectorAll('.savings-history-row input[type="checkbox"]').forEach((box) => {
      box.addEventListener('change', () => {
        const id = box.dataset.id;
        if (!id) return;
        if (box.checked) selectedSavingsIds.add(id);
        else selectedSavingsIds.delete(id);
        box.closest('.savings-history-row')?.classList.toggle('selected', box.checked);
        updateRemoveSavingsButton();
      });
    });

    updateRemoveSavingsButton();
  }

  function openSavingsHistory(from = 'pay') {
    savingsReturnView = from;
    selectedSavingsIds = new Set();
    renderSavingsHistory();
    showView('savings-history');
  }

  function removeSelectedSavings() {
    const api = savingsApi();
    if (!api || !selectedSavingsIds.size) return;
    api.removeByIds([...selectedSavingsIds]);
    selectedSavingsIds = new Set();
    renderSavingsHistory();
    renderSavingsUI(null);
  }

  function renderSavingsBanner() {
    const banner = $('savingsBanner');
    const api = savingsApi();
    if (!banner || !api) return;
    const { month } = api.getStats();
    if (!month.count) {
      banner.classList.add('hidden');
      banner.textContent = '';
      const paySub = $('paySub');
      if (paySub) paySub.classList.remove('hidden');
      return;
    }
    banner.innerHTML =
      t('savings.bannerMonth', { amount: `<strong>$${esc(api.formatUsd(month.reward_usd))}</strong>` }) +
      `<div class="savings-banner-sub">${esc(t('savings.bannerTimes', { count: month.count }))} · ${esc(t('savings.bannerHint'))}</div>`;
    banner.classList.remove('hidden');
    banner.disabled = false;
    const paySub = $('paySub');
    if (paySub) paySub.classList.add('hidden');
  }

  function renderWalletSavingsPanel() {
    const panel = $('walletSavingsPanel');
    const section = $('walletSavingsSection');
    const api = savingsApi();
    if (!panel || !api) return;
    const stats = api.getStats();
    if (!stats.allTime.count) {
      panel.classList.add('hidden');
      panel.innerHTML = '';
      section?.classList.add('hidden');
      $('btnWalletSavingsHistory')?.classList.add('hidden');
      return;
    }
    section?.classList.remove('hidden');
    const historyLink = $('btnWalletSavingsHistory');
    historyLink?.classList.remove('hidden');
    panel.innerHTML =
      renderSavingsStatRow('savings.month', stats.month) +
      renderSavingsStatRow('savings.quarter', stats.quarter) +
      renderSavingsStatRow('savings.allTime', stats.allTime) +
      `<p class="savings-disclaimer">${esc(
        t('savings.disclaimer', { default: `$${api.DEFAULT_AMOUNT}` }),
      )}</p>`;
    panel.classList.remove('hidden');
  }

  function renderSavingsUI(latestRewardUsd) {
    renderSavingsBanner();
    renderWalletSavingsPanel();
    const note = $('savingsResultNote');
    if (!note) return;
    if (latestRewardUsd == null) {
      note.classList.add('hidden');
      note.textContent = '';
      return;
    }
    const api = savingsApi();
    if (!api) return;
    const { month } = api.getStats();
    note.textContent = t('savings.resultAdded', {
      amount: api.formatUsd(latestRewardUsd),
      monthTotal: api.formatUsd(month.reward_usd),
    });
    note.classList.remove('hidden');
  }

  function recordSavingsLookup(data, best, amount_usd, pick) {
    const api = savingsApi();
    if (!api || !best) return;
    const merchant = data.merchant || {};
    const recorded = api.recordLookup({
      reward_usd: best.estimated_value_usd,
      purchase_amount_usd: amount_usd,
      amount_provided: amountProvided,
      merchant: merchant.merchantName || pick?.merchantName || '',
      card_name: best.card_name,
      category: data.resolved_category || pick?.spendBonusCategoryName || '',
    });
    renderSavingsUI(recorded.row?.reward_usd);
  }

  let catalog = [];
  let catalogByKey = {};
  let catalogImagesPromise = null;
  let issuerHints = [];
  function loadImageUrlCache() {
    try {
      const raw = localStorage.getItem(IMAGE_CACHE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveImageUrlCache() {
    try {
      localStorage.setItem(IMAGE_CACHE_KEY, JSON.stringify(imageCache));
    } catch (_) {}
  }

  function seedImageCache(entries) {
    let changed = false;
    (entries || []).forEach((row) => {
      const key = row?.card_key;
      const url = row?.image_url;
      if (key && url && imageCache[key] !== url) {
        imageCache[key] = url;
        changed = true;
      }
    });
    if (changed) saveImageUrlCache();
  }

  const imageCache = {};
  Object.assign(imageCache, loadImageUrlCache());
  let walletState = null; // { mode: 'local', cards: [] }
  let activeTab = 'name';
  let pendingAmount = DEFAULT_AMOUNT;
  let amountProvided = false;
  let selectedPick = null;
  let selectAllOnNextFocus = false;
  let manageDraft = [];
  let localSetupSelected = new Set();
  let userLocation = null; // { lat, lng } | null
  let merchantConfig = { googlePlacesEnabled: false, locationRecommended: false, nearbyStoresEnabled: false };
  const DEMO_CARD_KEYS = ['chase-sapphire-preferred', 'amex-gold', 'chase-freedom-unlimited'];

  function cardMetaFromKey(key) {
    const meta = catalogByKey[key] || {};
    return {
      card_key: key,
      card_name: meta.card_name || key,
      nickname: '',
      last4: '',
      image_url: meta.image_url || imageCache[key] || '',
    };
  }

  async function loadDemoWallet() {
    await ensureCatalogImages();
    const cards = DEMO_CARD_KEYS.map(cardMetaFromKey);
    saveLocalWallet(cards);
    walletState = { mode: 'local', cards };
    localSetupSelected = new Set(DEMO_CARD_KEYS);
  }

  function startSetupTour() {
    window.CR_ONBOARDING?.start('setup');
  }

  function maybeStartPayTour() {
    if (window.CR_ONBOARDING?.isComplete()) return;
    setTimeout(() => window.CR_ONBOARDING?.startPayTour(), 400);
  }

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
    const settingsBtn = $('btnWalletSettings');
    if (settingsBtn) settingsBtn.classList.toggle('hidden', name === 'language');
    const homeBtn = $('btnHome');
    if (homeBtn) homeBtn.classList.toggle('nav-home-muted', name === 'pay');
    window.CR_ANALYTICS?.trackScreen(name);
  }

  async function goHome() {
    if (!window.CR_I18N.hasChosenLocale()) {
      showView('language');
      return;
    }
    const payView = $('view-pay');
    if (payView && !payView.classList.contains('hidden')) {
      $('result')?.classList.remove('show');
      $('error')?.classList.remove('show');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    const w = resolveWallet();
    if (w) {
      walletState = w;
      await enterPayFlow();
      return;
    }
    showView('local-setup');
    await renderLocalCardTiles();
  }

  function loadPayTab() {
    try {
      const tab = localStorage.getItem(PAY_TAB_KEY);
      return tab === 'url' || tab === 'name' ? tab : 'name';
    } catch {
      return 'name';
    }
  }

  function savePayTab(tab) {
    try {
      localStorage.setItem(PAY_TAB_KEY, tab);
    } catch (_) {}
  }

  function loadLastMerchant() {
    try {
      const raw = localStorage.getItem(LAST_MERCHANT_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function saveLastMerchant(entry) {
    try {
      localStorage.setItem(LAST_MERCHANT_KEY, JSON.stringify(entry));
    } catch (_) {}
    updateLastMerchantChip();
  }

  function clearLastMerchant() {
    localStorage.removeItem(LAST_MERCHANT_KEY);
    updateLastMerchantChip();
  }

  function lastMerchantShortcutName(last) {
    if (!last) return '';
    if (last.tab === 'url' && last.merchantUrl) {
      try {
        return new URL(
          last.merchantUrl.includes('://') ? last.merchantUrl : `https://${last.merchantUrl}`,
        ).hostname.replace(/^www\./, '');
      } catch (_) {
        return last.merchantUrl;
      }
    }
    if (last.merchantName) return last.merchantName;
    return '';
  }

  function updateLastMerchantChip() {
    const storeBtn = $('btnLastMerchant');
    const urlBtn = $('btnLastMerchantUrl');
    const last = loadLastMerchant();
    [storeBtn, urlBtn].forEach((btn) => {
      if (!btn) return;
      btn.classList.add('hidden');
      btn.textContent = '';
    });
    if (!last) return;
    const name = lastMerchantShortcutName(last);
    if (!name) return;
    const label = t('pay.useLast', { name });
    if (last.tab === 'name' && last.merchantName && storeBtn) {
      storeBtn.textContent = label;
      storeBtn.classList.toggle('hidden', activeTab !== 'name');
    }
    if (last.tab === 'url' && last.merchantUrl && urlBtn) {
      urlBtn.textContent = label;
      urlBtn.classList.toggle('hidden', activeTab !== 'url');
    }
  }

  function applyLastMerchant() {
    const last = loadLastMerchant();
    if (!last) return;
    if (last.tab === 'url' || last.tab === 'name') {
      applyPayTab(last.tab);
    }
    if (last.tab === 'url' && last.merchantUrl) {
      $('merchantUrl').value = last.merchantUrl;
    }
    if (last.tab === 'name' && last.merchantName) {
      $('merchantName').value = last.merchantName;
    }
    if (last.amount != null && last.amount !== '') {
      applySavedAmount(last);
    }
    $('amount').focus();
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

  function resolveWallet() {
    const local = loadLocalWallet();
    if (local?.cards?.length) {
      walletState = { mode: 'local', cards: local.cards };
      seedImageCache(walletState.cards);
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
          if (activeTab === 'name') refreshNearbyStores();
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
    if (activeTab !== 'name' || userLocation) {
      el.classList.add('hidden');
      el.textContent = '';
      return;
    }
    el.textContent = t('loc.storeWarn');
    el.className = 'pay-mode-hint location-warn';
    el.classList.remove('hidden');
  }

  function purchaseChannelForTab() {
    return activeTab === 'url' ? 'online' : 'in_store';
  }

  function readAmountFromForm() {
    const raw = $('amount').value.trim();
    if (!raw) return { amount: DEFAULT_AMOUNT, provided: false };
    const n = parseFloat(raw);
    if (!Number.isFinite(n) || n <= 0) return { amount: DEFAULT_AMOUNT, provided: false };
    return { amount: n, provided: true };
  }

  function syncPendingAmount() {
    const parsed = readAmountFromForm();
    pendingAmount = parsed.amount;
    amountProvided = parsed.provided;
    return parsed;
  }

  function applySavedAmount(entry) {
    if (entry?.amount != null && entry.amount !== '') {
      $('amount').value = entry.amount;
    }
  }

  function formatResultMeta(amount_usd, storeLine, best) {
    const tail = `${storeLine} · ${best.multiplier}x · ${best.reason}`;
    if (amountProvided) return `$${amount_usd.toFixed(2)} · ${tail}`;
    return `${t('pay.amountEstimateNote', { amount: amount_usd.toFixed(0) })} · ${tail}`;
  }

  function formatPct(multiplier) {
    const n = Number(multiplier);
    if (Number.isInteger(n)) return String(n);
    return n.toFixed(1).replace(/\.0$/, '');
  }

  function formatRewardValue(rec) {
    const amount = rec.estimated_value_usd.toFixed(2);
    if (rec.valuate_as_points) {
      return t('result.pointsValue', {
        points: Math.round(rec.points_earned),
        amount,
      });
    }
    return t('result.cashValue', { pct: formatPct(rec.multiplier), amount });
  }

  function formatRankValue(rec) {
    const amount = rec.estimated_value_usd.toFixed(2);
    if (rec.valuate_as_points) {
      return t('result.rankPoints', {
        points: Math.round(rec.points_earned),
        amount,
      });
    }
    return t('result.rankCash', { amount });
  }

  function formatRankSub(rec) {
    if (rec.valuate_as_points) {
      const pts = Math.round(rec.points_earned);
      const mult = formatPct(rec.multiplier);
      if (rec.partner_bonus) {
        return t('result.rankPartnerEarn', { mult, pts });
      }
      return `${mult}x · ${pts} pts · ${rec.reason}`;
    }
    return `${formatPct(rec.multiplier)}% · ${rec.reason}`;
  }

  function renderPartnerNotes(rankings, merchantName) {
    const el = $('partnerNotes');
    if (!el) return;
    const notes = (rankings || []).filter((r) => r.partner_bonus && r.rank > 1);
    if (!notes.length || !merchantName) {
      el.classList.add('hidden');
      el.innerHTML = '';
      return;
    }
    el.classList.remove('hidden');
    el.innerHTML = notes
      .map((r) =>
        `<p class="partner-note">${esc(
          t('result.partnerRankNote', {
            card: r.card_name,
            mult: formatPct(r.multiplier),
            pts: Math.round(r.points_earned),
            rank: r.rank,
            merchant: merchantName,
          })
        )}</p>`
      )
      .join('');
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

  async function openWalletView() {
    manageDraft = (walletState?.cards || []).map((c) => ({ ...c }));
    if (!catalog.length) await loadCatalog();
    await loadIssuerHints();
    renderManageList();
    renderManageQuickAdd();
    $('issuerResults').innerHTML = '';
    $('issuerQuery').value = '';
    $('manageError').classList.remove('show');
    showView('manage');
    renderWalletSavingsPanel();
  }

  function applyPayTab(tab) {
    activeTab = tab === 'url' ? 'url' : 'name';
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === activeTab));
    $('panel-url').classList.toggle('active', activeTab === 'url');
    $('panel-name').classList.toggle('active', activeTab === 'name');
    savePayTab(activeTab);
    updateLocationStatus();
    updateLastMerchantChip();
    if (activeTab === 'name') refreshNearbyStores();
    else hideStoreAssistPanels();
  }

  function hideNearbyStores() {
    const panel = $('nearbyStores');
    if (panel) panel.classList.add('hidden');
  }

  function hideStoreAssistPanels() {
    hideMerchantSuggestions();
    hideNearbyStores();
  }

  function formatDistance(meters) {
    if (meters == null || Number.isNaN(meters)) return '';
    if (meters < 1000) return `${Math.round(meters)} m`;
    return `${(meters / 1000).toFixed(1)} km`;
  }

  function renderNearbyStoresList(places = nearbyPlaces) {
    const list = $('nearbyStoresList');
    const panel = $('nearbyStores');
    if (!list || !panel) return;
    const visible = nearbyPlacesForInput(places);
    if (!visible.length) {
      panel.classList.add('hidden');
      return;
    }
    list.innerHTML = visible
      .map(
        (p, i) => `
      <button type="button" class="nearby-chip" data-idx="${nearbyPlaces.indexOf(p)}" title="${esc(p.displayName)}">
        ${esc(p.displayName)}${p.distanceMeters != null ? ` · ${esc(formatDistance(p.distanceMeters))}` : ''}
      </button>`,
      )
      .join('');
    list.querySelectorAll('.nearby-chip').forEach((btn) => {
      btn.addEventListener('click', () => selectNearbyStore(nearbyPlaces[Number(btn.dataset.idx)]));
    });
    panel.classList.remove('hidden');
  }

  async function refreshNearbyStores() {
    const panel = $('nearbyStores');
    const list = $('nearbyStoresList');
    if (!panel || !list || activeTab !== 'name') {
      hideNearbyStores();
      return;
    }
    if (!merchantConfig.nearbyStoresEnabled && !merchantConfig.googlePlacesEnabled) {
      hideNearbyStores();
      return;
    }
    if (!userLocation) {
      hideNearbyStores();
      return;
    }
    list.innerHTML = '';
    panel.classList.remove('hidden');
    try {
      const { lat, lng } = userLocation;
      const res = await fetch(
        `/api/merchant/nearby?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lng)}&limit=5`,
      );
      const data = await res.json();
      if (!res.ok || !(data.places || []).length) {
        hideNearbyStores();
        nearbyPlaces = [];
        return;
      }
      nearbyPlaces = data.places;
      renderNearbyStoresList();
    } catch (_) {
      hideNearbyStores();
      nearbyPlaces = [];
    }
  }

  async function selectNearbyStore(place) {
    if (!place) return;
    $('merchantName').value = place.displayName || place.merchantName || '';
    hideMerchantSuggestions();
    hideNearbyStores();
    syncPendingAmount();
    const go = $('go');
    const errorEl = $('error');
    errorEl.classList.remove('show');
    $('result').classList.remove('show');
    go.disabled = true;
    try {
      await runRecommend(
        {
          merchantId: place.merchantId,
          merchantName: place.merchantName || place.displayName,
          spendBonusCategoryName: place.spendBonusCategoryName,
        },
        pendingAmount,
      );
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.add('show');
    } finally {
      go.disabled = false;
    }
  }

  async function loadCatalog() {
    const res = await fetch('/api/cards');
    const data = await res.json();
    catalog = data.cards || [];
    catalogByKey = Object.fromEntries(catalog.map((c) => [c.card_key, c]));
    seedImageCache(catalog);
    updatePaySub();
  }

  function cardMeta(cardKey, fallbackName) {
    const fromCatalog = catalogByKey[cardKey] || {};
    const fromWallet = (manageDraft || []).find((c) => c.card_key === cardKey) || {};
    return {
      card_key: cardKey,
      card_name: fromWallet.card_name || fromCatalog.card_name || fallbackName || cardKey,
      issuer: fromCatalog.issuer || '',
      image_url: fromWallet.image_url || fromCatalog.image_url || '',
    };
  }

  function cardThumbHtml(meta, { small = false, eager = false } = {}) {
    const name = meta.card_name || meta.card_key;
    const cls = small ? 'card-thumb card-thumb-sm' : 'card-thumb';
    const key = esc(meta.card_key);
    const slotCls = small ? 'card-thumb-slot card-thumb-sm' : 'card-thumb-slot';
    const cached = imageCache[meta.card_key] || meta.image_url;
    const loading = eager ? 'eager' : 'lazy';
    if (cached) {
      return `<div class="${slotCls}" data-card-key="${key}"><img class="${cls}" src="${esc(cached)}" alt="${esc(name)}" loading="${loading}" decoding="async" /></div>`;
    }
    const initial = (name.replace(/[^A-Za-z0-9]/g, '').charAt(0) || '?').toUpperCase();
    return `<div class="${slotCls}" data-card-key="${key}"><div class="${cls} card-thumb-fallback" aria-hidden="true">${esc(initial)}</div></div>`;
  }

  function browserPreloadImages(urls) {
    const unique = [...new Set(urls.filter(Boolean))];
    return Promise.all(
      unique.map(
        (url) =>
          new Promise((resolve) => {
            const img = new Image();
            img.onload = () => resolve(true);
            img.onerror = () => resolve(false);
            img.src = url;
          }),
      ),
    );
  }

  async function fetchMissingImageUrls(keys) {
    const need = keys.filter((k) => k && !imageCache[k] && !catalogByKey[k]?.image_url);
    if (!need.length) return;
    try {
      const res = await fetch('/api/cards/images', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ card_keys: need.slice(0, 48) }),
      });
      const data = await res.json();
      if (!res.ok) return;
      Object.assign(imageCache, data.images || {});
      saveImageUrlCache();
    } catch (_) {}
  }

  function imageUrlForKey(cardKey) {
    return imageCache[cardKey] || catalogByKey[cardKey]?.image_url || '';
  }

  async function ensureCatalogImages() {
    if (!catalogImagesPromise) {
      catalogImagesPromise = (async () => {
        if (!catalog.length) await loadCatalog();
        const keys = catalog.map((c) => c.card_key);
        await fetchMissingImageUrls(keys);
        await browserPreloadImages(keys.map((k) => imageUrlForKey(k)));
      })();
    }
    return catalogImagesPromise;
  }

  async function hydrateCardImages(rootEl) {
    if (!rootEl) return;
    const keys = [
      ...new Set(
        [...rootEl.querySelectorAll('[data-card-key]')]
          .map((el) => el.dataset.cardKey)
          .filter(Boolean),
      ),
    ];
    await fetchMissingImageUrls(keys);
    rootEl.querySelectorAll('[data-card-key]').forEach((slot) => {
      const url = imageUrlForKey(slot.dataset.cardKey);
      if (!url) return;
      const name =
        slot.closest('.manage-row')?.querySelector('strong')?.textContent ||
        slot.closest('.card-tile')?.querySelector('.card-tile-name')?.textContent ||
        slot.dataset.cardKey;
      const cls = slot.classList.contains('card-thumb-sm') ? 'card-thumb card-thumb-sm' : 'card-thumb';
      slot.innerHTML = `<img class="${cls}" src="${esc(url)}" alt="${esc(name)}" loading="eager" decoding="async" />`;
    });
  }

  function cardTileHtml(card, { inWallet = false, selected = false } = {}) {
    const meta = cardMeta(card.card_key, card.card_name);
    const disabled = inWallet ? ' in-wallet' : '';
    const sel = selected ? ' selected' : '';
    return `<button type="button" class="card-tile${disabled}${sel}" data-key="${esc(card.card_key)}" ${inWallet ? 'disabled' : ''}>
      ${cardThumbHtml(meta, { eager: true })}
      <div class="card-tile-name">${esc(meta.card_name)}</div>
    </button>`;
  }

  function toggleLocalSetupCard(cardKey, btn) {
    if (localSetupSelected.has(cardKey)) {
      localSetupSelected.delete(cardKey);
      btn?.classList.remove('selected');
    } else {
      localSetupSelected.add(cardKey);
      btn?.classList.add('selected');
    }
    syncLocalSetupTileSelection(cardKey);
  }

  function syncLocalSetupTileSelection(cardKey) {
    const selected = localSetupSelected.has(cardKey);
    $('localCardPicker')
      ?.querySelector(`.card-tile[data-key="${cardKey}"]`)
      ?.classList.toggle('selected', selected);
    $('setupIssuerResults')
      ?.querySelectorAll(`.card-tile[data-key="${cardKey}"]`)
      .forEach((el) => el.classList.toggle('selected', selected));
  }

  async function renderLocalCardTiles() {
    const grid = $('localCardPicker');
    if (!grid) return;
    await ensureCatalogImages();
    await loadIssuerHints();
    localSetupSelected = new Set();
    grid.innerHTML = catalog.map((c) => cardTileHtml(c)).join('');
    grid.querySelectorAll('.card-tile').forEach((btn) => {
      btn.addEventListener('click', () => {
        toggleLocalSetupCard(btn.dataset.key, btn);
      });
    });
    await hydrateCardImages(grid);
    const setupResults = $('setupIssuerResults');
    if (setupResults) setupResults.innerHTML = '';
    const setupQuery = $('setupIssuerQuery');
    if (setupQuery) setupQuery.value = '';
  }

  async function searchSetupIssuerCards() {
    const q = ($('setupIssuerQuery')?.value || '').trim();
    const resultsEl = $('setupIssuerResults');
    const errorEl = $('localSetupError');
    if (!resultsEl) return;
    errorEl?.classList.remove('show');
    if (q.length < 2) {
      if (errorEl) {
        errorEl.textContent = t('wallet.errorIssuerLen');
        errorEl.classList.add('show');
      }
      resultsEl.innerHTML = '';
      return;
    }
    resultsEl.innerHTML = '<p class="hints">' + esc(t('wallet.searching')) + '</p>';
    try {
      const res = await fetch(`/api/cards/by-issuer?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Search failed');
      const matches = data.matches || [];
      if (!matches.length) {
        resultsEl.innerHTML = '<p class="hints">' + esc(t('wallet.noIssuerMatch')) + '</p>';
        return;
      }
      matches.forEach((c) => {
        catalogByKey[c.card_key] = { ...catalogByKey[c.card_key], ...c };
        if (c.image_url) imageCache[c.card_key] = c.image_url;
      });
      resultsEl.innerHTML = matches
        .map((c) =>
          cardTileHtml(c, { selected: localSetupSelected.has(c.card_key) }),
        )
        .join('');
      resultsEl.querySelectorAll('.card-tile').forEach((btn) => {
        btn.addEventListener('click', () => toggleLocalSetupCard(btn.dataset.key, btn));
      });
      await hydrateCardImages(resultsEl);
    } catch (err) {
      resultsEl.innerHTML = '';
      if (errorEl) {
        errorEl.textContent = err.message;
        errorEl.classList.add('show');
      }
    }
  }

  function activeInputEl() {
    return activeTab === 'url' ? $('merchantUrl') : $('merchantName');
  }

  function markInputsForReentry() {
    selectAllOnNextFocus = true;
  }

  function normalizeStoreName(text) {
    return (text || '')
      .trim()
      .toLowerCase()
      .replace(/[^\w\s']/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function storeNamesMatch(a, b) {
    const left = normalizeStoreName(a);
    const right = normalizeStoreName(b);
    if (!left || !right) return false;
    if (left === right) return true;
    if (left.length >= 4 && right.length >= 4) {
      return left.startsWith(right) || right.startsWith(left);
    }
    return false;
  }

  function merchantNameInputValue() {
    return ($('merchantName')?.value || '').trim();
  }

  function hideMerchantSuggestions() {
    $('merchantSuggestions')?.classList.add('hidden');
  }

  function renderMerchantSuggestions(items) {
    const panel = $('merchantSuggestions');
    if (!panel) return;
    const query = merchantNameInputValue();
    if (query.length < 2) {
      hideMerchantSuggestions();
      return;
    }
    const filtered = (items || []).filter((m) => {
      const name = m.name || '';
      return name && !storeNamesMatch(query, name);
    });
    if (!filtered.length) {
      hideMerchantSuggestions();
      return;
    }
    panel.innerHTML = filtered
      .slice(0, 6)
      .map((m) => {
        const cat = m.category || m.inStoreCategory || '';
        return `<button type="button" class="merchant-suggest-row" data-name="${esc(m.name)}" role="option">
          ${esc(m.name)}${cat ? `<span class="merchant-suggest-meta">${esc(cat)}</span>` : ''}
        </button>`;
      })
      .join('');
    panel.querySelectorAll('.merchant-suggest-row').forEach((btn) => {
      btn.addEventListener('click', () => {
        $('merchantName').value = btn.dataset.name || '';
        hideMerchantSuggestions();
        updateNearbyForInput();
        markInputsForReentry();
      });
    });
    panel.classList.remove('hidden');
  }

  let suggestTimer = null;
  async function refreshMerchantSuggestions(query) {
    const q = (query || '').trim();
    if (q.length < 2) {
      hideMerchantSuggestions();
      return;
    }
    const channel = purchaseChannelForTab();
    try {
      const res = await fetch(
        `/api/merchants?q=${encodeURIComponent(q)}&purchase_channel=${encodeURIComponent(channel)}`,
      );
      const data = await res.json();
      if (!res.ok) {
        hideMerchantSuggestions();
        return;
      }
      renderMerchantSuggestions(data.suggestions || []);
    } catch (_) {
      hideMerchantSuggestions();
    }
  }

  function syncMerchantSuggestionsSoon() {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(() => refreshMerchantSuggestions(merchantNameInputValue()), 200);
  }

  function nearbyPlacesForInput(places = nearbyPlaces) {
    const query = merchantNameInputValue();
    if (!query) return places;
    return places.filter((p) => !storeNamesMatch(query, p.displayName || p.merchantName || ''));
  }

  function updateNearbyForInput() {
    if (activeTab !== 'name') {
      hideNearbyStores();
      return;
    }
    renderNearbyStoresList(nearbyPlacesForInput());
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
    if (c === 'high') return t('conf.high');
    if (c === 'medium') return t('conf.medium');
    return t('conf.low');
  }

  function channelSuffix(purchaseChannel) {
    if (purchaseChannel === 'online') return t('modal.online');
    if (purchaseChannel === 'in_store') return t('modal.inStore');
    return '';
  }

  function shouldConfirmMerchant(data) {
    const alts = (data.candidates || []).filter((c) => c.merchantId !== data.best?.merchantId);
    if (!data.needsConfirmation) return false;
    if (data.best?.confidence === 'high' && !alts.length) return false;
    return true;
  }

  function showConfirmModal(data) {
    activeInputEl().blur();
    const best = data.best;
    selectedPick = best;

    $('confirmMerchant').textContent = best.merchantName;
    $('confirmCategory').textContent = `→ ${best.spendBonusCategoryName}${channelSuffix(data.purchaseChannel)}`;
    $('confirmMeta').textContent = confidenceLabel(best.confidence);

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
          $('confirmCategory').textContent = `→ ${selectedPick.spendBonusCategoryName}${channelSuffix(data.purchaseChannel)}`;
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

  function rememberLastMerchantFromForm() {
    const entry = {
      tab: activeTab,
    };
    if (amountProvided) entry.amount = pendingAmount;
    if (activeTab === 'url') {
      entry.merchantUrl = $('merchantUrl').value.trim();
    } else {
      entry.merchantName = $('merchantName').value.trim();
    }
    saveLastMerchant(entry);
  }

  async function runRecommend(pick, amount_usd) {
    const errorEl = $('error');
    const resultEl = $('result');
    const go = $('go');
    errorEl.classList.remove('show');
    resultEl.classList.remove('show');

    const keys = walletCardKeys();
    if (!keys.length) {
      throw new Error(t('pay.errorNoCards'));
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
    if (!res.ok) throw new Error(data.detail || t('pay.errorRequest'));

    rememberLastMerchantFromForm();

    const best = data.best;
    const merchant = data.merchant || {};
    $('bestName').textContent = best.card_name;
    $('bestValue').textContent = formatRewardValue(best);
    const storeLine = merchant.merchantName
      ? `${merchant.merchantName} → ${data.resolved_category}`
      : data.resolved_category;
    $('bestMeta').textContent = formatResultMeta(amount_usd, storeLine, best);
    $('btnValuationHelp').classList.remove('hidden');
    $('rankHead').textContent = t('result.rankHead', { count: data.card_count });
    $('rankings').innerHTML = data.rankings
      .map(
        (r) => `
        <div class="rank-row ${r.rank === 1 ? 'top' : ''} ${r.partner_bonus ? 'partner-earn' : ''}">
          <div class="rank-num">#${r.rank}</div>
          <div>
            <div class="rank-name">${esc(r.card_name)}${
              r.partner_bonus
                ? `<span class="partner-badge">${esc(t('result.partnerBadge'))}</span>`
                : ''
            }</div>
            <div class="rank-sub">${esc(formatRankSub(r))}</div>
          </div>
          <div class="rank-usd">${esc(formatRankValue(r))}</div>
        </div>`
      )
      .join('');
    renderPartnerNotes(data.rankings, merchant.merchantName || '');
    resultEl.classList.add('show');
    recordSavingsLookup(data, best, amount_usd, pick);
    window.CR_ANALYTICS?.track('recommend', {
      merchant_name: merchant.merchantName || pick.merchantName || '',
      amount_usd,
      card_count: data.card_count,
      best_card: best.card_key || best.card_name || '',
      partner_bonus: !!best.partner_bonus,
      resolved_category: data.resolved_category || '',
    });
    resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    markInputsForReentry();
  }

  function renderManageList() {
    const list = $('manageCardList');
    list.innerHTML = manageDraft
      .map((c, i) => {
        const meta = cardMeta(c.card_key, c.card_name);
        return `
      <div class="manage-row" data-idx="${i}">
        ${cardThumbHtml(meta, { small: true })}
        <div class="manage-row-main">
          <div class="manage-row-head">
            <strong>${esc(meta.card_name)}</strong>
            <button type="button" class="link-btn remove-card" data-idx="${i}">${esc(t('wallet.remove'))}</button>
          </div>
          ${meta.issuer ? `<div class="manage-row-sub">${esc(meta.issuer)}</div>` : ''}
        </div>
      </div>`;
      })
      .join('');
    list.querySelectorAll('.remove-card').forEach((btn) => {
      btn.addEventListener('click', async () => {
        $('manageError').classList.remove('show');
        if (manageDraft.length <= 1) {
          $('manageError').textContent = t('wallet.errorMin');
          $('manageError').classList.add('show');
          return;
        }
        manageDraft.splice(Number(btn.dataset.idx), 1);
        try {
          await persistManageDraft();
          renderManageList();
          renderManageQuickAdd();
        } catch (err) {
          $('manageError').textContent = err.message;
          $('manageError').classList.add('show');
        }
      });
    });
    hydrateCardImages(list);
  }

  function renderManageQuickAdd() {
    const grid = $('manageQuickAdd');
    const inWallet = new Set(manageDraft.map((c) => c.card_key));
    const available = catalog.filter((c) => !inWallet.has(c.card_key));
    grid.innerHTML = available.map((c) => cardTileHtml(c)).join('');
    grid.querySelectorAll('.card-tile:not(.in-wallet)').forEach((btn) => {
      btn.addEventListener('click', () => addCardToWallet(btn.dataset.key));
    });
    void hydrateCardImages(grid);
  }

  async function loadIssuerHints() {
    try {
      const res = await fetch('/api/cards/issuers');
      const data = await res.json();
      issuerHints = data.issuers || [];
      $('issuer-hints').innerHTML = issuerHints.map((i) => `<option value="${esc(i)}">`).join('');
    } catch (_) {
      issuerHints = [];
    }
  }

  async function searchIssuerCards() {
    const q = $('issuerQuery').value.trim();
    const resultsEl = $('issuerResults');
    $('manageError').classList.remove('show');
    if (q.length < 2) {
      $('manageError').textContent = t('wallet.errorIssuerLen');
      $('manageError').classList.add('show');
      resultsEl.innerHTML = '';
      return;
    }
    resultsEl.innerHTML = '<p class="hints">' + esc(t('wallet.searching')) + '</p>';
    try {
      const res = await fetch(`/api/cards/by-issuer?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Search failed');
      const inWallet = new Set(manageDraft.map((c) => c.card_key));
      const matches = (data.matches || []).filter((c) => !inWallet.has(c.card_key));
      if (!matches.length) {
        resultsEl.innerHTML = '<p class="hints">' + esc(t('wallet.noIssuerMatch')) + '</p>';
        return;
      }
      matches.forEach((c) => {
        catalogByKey[c.card_key] = { ...catalogByKey[c.card_key], ...c };
        if (c.image_url) imageCache[c.card_key] = c.image_url;
      });
      resultsEl.innerHTML = matches.map((c) => cardTileHtml(c)).join('');
      resultsEl.querySelectorAll('.card-tile').forEach((btn) => {
        btn.addEventListener('click', () => addCardToWallet(btn.dataset.key, catalogByKey[btn.dataset.key]));
      });
      await hydrateCardImages(resultsEl);
    } catch (err) {
      resultsEl.innerHTML = '';
      $('manageError').textContent = err.message;
      $('manageError').classList.add('show');
    }
  }

  async function addCardToWallet(cardKey, metaOverride) {
    $('manageError').classList.remove('show');
    if (manageDraft.some((c) => c.card_key === cardKey)) return;
    const meta = metaOverride || catalogByKey[cardKey] || {};
    manageDraft.push({
      card_key: cardKey,
      card_name: meta.card_name || cardKey,
      nickname: '',
      last4: '',
      image_url: meta.image_url || imageCache[cardKey] || '',
    });
    try {
      await persistManageDraft();
      renderManageList();
      renderManageQuickAdd();
      const resultsEl = $('issuerResults');
      if (resultsEl) {
        resultsEl.querySelectorAll(`.card-tile[data-key="${cardKey}"]`).forEach((el) => {
          el.classList.add('in-wallet');
          el.disabled = true;
        });
      }
    } catch (err) {
      manageDraft.pop();
      $('manageError').textContent = err.message;
      $('manageError').classList.add('show');
    }
  }

  async function persistManageDraft() {
    if (!manageDraft.length) throw new Error(t('wallet.errorMin'));
    saveLocalWallet(manageDraft);
    walletState = { mode: 'local', cards: manageDraft.map((c) => ({ ...c })) };
    updatePaySub();
    await loadCatalog();
    window.CR_ANALYTICS?.track('wallet_save', { card_count: manageDraft.length });
  }

  async function enterPayFlow({ startPayTour = true } = {}) {
    await loadCatalog();
    applyPayTab(loadPayTab());
    applyPageI18n();
    showView('pay');
    renderSavingsBanner();
    if (activeTab === 'name' && !userLocation) {
      await requestUserLocation();
    }
    updateLocationStatus();
    updateLastMerchantChip();
    if (activeTab === 'name') await refreshNearbyStores();
    else hideNearbyStores();
    if (startPayTour) maybeStartPayTour();
  }

  function continueAfterLanguage() {
    applyPageI18n();
    const w = resolveWallet();
    if (w) {
      walletState = w;
      enterPayFlow({ startPayTour: !window.CR_ONBOARDING?.isComplete() });
    } else {
      void (async () => {
        await ensureCatalogImages();
        showView('local-setup');
        await renderLocalCardTiles();
        startSetupTour();
      })();
    }
  }

  function finishLanguagePick(code) {
    window.CR_I18N.setLocale(code);
    window.CR_ANALYTICS?.track('language_pick', { locale: code });
    if (languageReturnView === 'wallet') {
      applyPageI18n();
      showView('manage');
      return;
    }
    continueAfterLanguage();
  }

  async function init() {
    bindReentryInput($('merchantUrl'));
    bindReentryInput($('merchantName'));
    $('merchantName').addEventListener('input', () => {
      syncMerchantSuggestionsSoon();
      updateNearbyForInput();
    });
    $('merchantName').addEventListener('blur', () => {
      setTimeout(hideMerchantSuggestions, 160);
    });
    bindReentryInput($('amount'));

    document.querySelectorAll('.tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        applyPayTab(btn.dataset.tab);
      });
    });

    document.querySelectorAll('.lang-btn').forEach((btn) => {
      btn.addEventListener('click', () => finishLanguagePick(btn.dataset.lang));
    });

    $('btnChangeLanguage')?.addEventListener('click', () => {
      languageReturnView = 'wallet';
      showView('language');
    });

    $('btnLastMerchant')?.addEventListener('click', () => applyLastMerchant());
    $('btnLastMerchantUrl')?.addEventListener('click', () => applyLastMerchant());

    $('localSave').addEventListener('click', () => {
      if (!localSetupSelected.size) {
        $('localSetupError').textContent = t('setup.errorMin');
        $('localSetupError').classList.add('show');
        return;
      }
      const cards = [...localSetupSelected].map((key) => {
        const meta = catalogByKey[key] || {};
        return {
          card_key: key,
          card_name: meta.card_name || key,
          nickname: '',
          last4: '',
          image_url: meta.image_url || imageCache[key] || '',
        };
      });
      saveLocalWallet(cards);
      walletState = { mode: 'local', cards };
      $('localSetupError').classList.remove('show');
      window.CR_ANALYTICS?.track('setup_complete', { card_count: cards.length });
      enterPayFlow();
    });

    $('btnReplayTour')?.addEventListener('click', () => {
      showView('pay');
      window.CR_ONBOARDING?.startPayTour({ force: true });
    });

    window.CR_ONBOARDING?.registerTryDemo(async () => {
      await loadDemoWallet();
      await enterPayFlow({ startPayTour: false });
      const nameInput = $('merchantName');
      if (nameInput) nameInput.value = 'Chipotle';
      const amountInput = $('amount');
      if (amountInput) amountInput.value = '25';
      pendingAmount = 25;
      amountProvided = true;
      syncPendingAmount();
    });

    $('btnWalletSettings').addEventListener('click', () => openWalletView());
    $('btnHome')?.addEventListener('click', () => goHome());

    $('savingsBanner')?.addEventListener('click', () => openSavingsHistory('pay'));
    $('btnWalletSavingsHistory')?.addEventListener('click', () => openSavingsHistory('manage'));
    $('savingsHistoryBack')?.addEventListener('click', () => showView(savingsReturnView));
    $('btnRemoveSavingsSelected')?.addEventListener('click', () => removeSelectedSavings());

    $('manageBack').addEventListener('click', () => showView('pay'));
    $('issuerSearchBtn').addEventListener('click', () => searchIssuerCards());
    $('setupIssuerSearchBtn')?.addEventListener('click', () => searchSetupIssuerCards());
    $('issuerQuery').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        searchIssuerCards();
      }
    });
    $('setupIssuerQuery')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        searchSetupIssuerCards();
      }
    });

    let issuerDebounce = null;
    $('issuerQuery').addEventListener('input', () => {
      clearTimeout(issuerDebounce);
      issuerDebounce = setTimeout(() => {
        const q = $('issuerQuery').value.trim();
        if (q.length >= 2) searchIssuerCards();
      }, 300);
    });

    let setupIssuerDebounce = null;
    $('setupIssuerQuery')?.addEventListener('input', () => {
      clearTimeout(setupIssuerDebounce);
      setupIssuerDebounce = setTimeout(() => {
        const q = $('setupIssuerQuery').value.trim();
        if (q.length >= 2) searchSetupIssuerCards();
      }, 300);
    });

    $('btnResetLocal').addEventListener('click', () => {
      $('resetModal').classList.add('show');
    });

    function performLocalReset() {
      clearLocalWallet();
      localStorage.removeItem(IMAGE_CACHE_KEY);
      clearLastMerchant();
      savingsApi()?.clear();
      Object.keys(imageCache).forEach((k) => delete imageCache[k]);
      walletState = null;
      renderSavingsUI(null);
      $('resetModal').classList.remove('show');
      window.CR_ONBOARDING?.reset();
      showView('local-setup');
      void renderLocalCardTiles().then(() => startSetupTour());
    }

    $('resetConfirm').addEventListener('click', () => performLocalReset());
    $('resetCancel').addEventListener('click', () => $('resetModal').classList.remove('show'));
    $('resetModal').addEventListener('click', (e) => {
      if (e.target.id === 'resetModal') $('resetModal').classList.remove('show');
    });

    $('btnValuationHelp').addEventListener('click', () => {
      $('valuationModal').classList.add('show');
      $('valuationModal').setAttribute('aria-hidden', 'false');
    });
    $('valuationClose').addEventListener('click', () => {
      $('valuationModal').classList.remove('show');
      $('valuationModal').setAttribute('aria-hidden', 'true');
    });
    $('valuationModal').addEventListener('click', (e) => {
      if (e.target.id === 'valuationModal') {
        $('valuationModal').classList.remove('show');
        $('valuationModal').setAttribute('aria-hidden', 'true');
      }
    });

    $('form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const errorEl = $('error');
      const go = $('go');
      const submitLabel = go.textContent;
      errorEl.classList.remove('show');
      $('result').classList.remove('show');
      go.disabled = true;
      go.textContent = t('pay.submitting');
      syncPendingAmount();
      const body = {};
      if (activeTab === 'url') {
        const url = $('merchantUrl').value.trim();
        if (!url) {
          errorEl.textContent = t('pay.errorUrl');
          errorEl.classList.add('show');
          go.disabled = false;
          return;
        }
        body.merchant_url = url;
      } else {
        const name = $('merchantName').value.trim();
        if (!name) {
          errorEl.textContent = t('pay.errorStore');
          errorEl.classList.add('show');
          go.disabled = false;
          return;
        }
        body.merchant_name = name;
      }
      try {
        const res = await fetch('/api/merchant/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(attachLocationToBody(body)),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || t('pay.errorRequest'));
        rememberLastMerchantFromForm();
        window.CR_ANALYTICS?.track('merchant_resolve', {
          merchant_name: data.best?.merchantName || body.merchant_name || '',
          candidates: (data.candidates || []).length,
        });
        if (shouldConfirmMerchant(data)) showConfirmModal(data);
        else await runRecommend(data.best, pendingAmount);
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.add('show');
      } finally {
        go.disabled = false;
        go.textContent = submitLabel || t('pay.submit');
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

    await loadCatalog();
    void ensureCatalogImages();

    if (!window.CR_I18N.hasChosenLocale()) {
      languageReturnView = 'bootstrap';
      showView('language');
      return;
    }

    window.CR_I18N.setLocale(window.CR_I18N.loadLocale());
    applyPageI18n();
    const w = resolveWallet();
    if (w) enterPayFlow({ startPayTour: !window.CR_ONBOARDING?.isComplete() });
    else {
      showView('local-setup');
      await renderLocalCardTiles();
      startSetupTour();
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
