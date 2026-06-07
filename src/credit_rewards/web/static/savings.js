(() => {
  const STORAGE_KEY = 'creditrewards_savings_v1';
  const DEFAULT_AMOUNT = 100;

  function newId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  }

  function normalizeLookups(lookups) {
    return (lookups || []).map((row, i) => ({
      ...row,
      id: row.id || `legacy-${row.ts}-${i}`,
    }));
  }

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const data = raw ? JSON.parse(raw) : null;
      return normalizeLookups(Array.isArray(data?.lookups) ? data.lookups : []);
    } catch {
      return [];
    }
  }

  function save(lookups) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ lookups: normalizeLookups(lookups) }));
    } catch (_) {}
  }

  function startOfMonth(d = new Date()) {
    return new Date(d.getFullYear(), d.getMonth(), 1).getTime();
  }

  function startOfQuarter(d = new Date()) {
    const qMonth = Math.floor(d.getMonth() / 3) * 3;
    return new Date(d.getFullYear(), qMonth, 1).getTime();
  }

  function aggregate(lookups, sinceTs) {
    const rows = lookups.filter((row) => row.ts >= sinceTs);
    return {
      reward_usd: rows.reduce((sum, row) => sum + (row.reward_usd || 0), 0),
      count: rows.length,
      default_amount_count: rows.filter((row) => !row.amount_provided).length,
    };
  }

  function getStats(now = new Date()) {
    const lookups = load();
    const month = aggregate(lookups, startOfMonth(now));
    const quarter = aggregate(lookups, startOfQuarter(now));
    const allTime = aggregate(lookups, 0);
    return { lookups, month, quarter, allTime, defaultAmount: DEFAULT_AMOUNT };
  }

  function listAll() {
    return load().slice().sort((a, b) => b.ts - a.ts);
  }

  function recordLookup(entry) {
    const lookups = load();
    const row = {
      id: newId(),
      ts: Date.now(),
      reward_usd: Number(entry.reward_usd) || 0,
      purchase_amount_usd: Number(entry.purchase_amount_usd) || DEFAULT_AMOUNT,
      amount_provided: Boolean(entry.amount_provided),
      merchant: String(entry.merchant || '').slice(0, 120),
      card_name: String(entry.card_name || '').slice(0, 120),
      category: String(entry.category || '').slice(0, 80),
    };
    if (row.reward_usd <= 0) return { row: null, stats: getStats() };
    lookups.push(row);
    save(lookups);
    return { row, stats: getStats() };
  }

  function removeByIds(ids) {
    const drop = new Set(ids || []);
    const kept = load().filter((row) => !drop.has(row.id));
    save(kept);
    return getStats();
  }

  function clear() {
    localStorage.removeItem(STORAGE_KEY);
  }

  function formatUsd(amount) {
    const n = Number(amount) || 0;
    return n.toFixed(2);
  }

  window.CR_SAVINGS = {
    DEFAULT_AMOUNT,
    load,
    save,
    getStats,
    listAll,
    recordLookup,
    removeByIds,
    clear,
    formatUsd,
  };
})();
