(() => {
  const DISMISS_KEY = 'paycue_install_dismiss_v1';

  function isStandalone() {
    return (
      window.matchMedia('(display-mode: standalone)').matches
      || window.navigator.standalone === true
    );
  }

  function isIos() {
    const ua = window.navigator.userAgent;
    return (
      /iPad|iPhone|iPod/.test(ua)
      || (window.navigator.platform === 'MacIntel' && window.navigator.maxTouchPoints > 1)
    );
  }

  function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
  }

  function setupInstallBanner() {
    const banner = document.getElementById('installBanner');
    const dismiss = document.getElementById('installDismiss');
    if (!banner || !dismiss) return;

    if (isStandalone()) return;
    try {
      if (localStorage.getItem(DISMISS_KEY) === '1') return;
    } catch (_) {
      return;
    }

    const msg = document.getElementById('installBannerText');
    if (msg) {
      const key = isIos() ? 'pwa.installIos' : 'pwa.installGeneric';
      msg.textContent = window.CR_I18N?.t(key) || msg.textContent;
    }

    banner.classList.remove('hidden');

    dismiss.addEventListener('click', () => {
      banner.classList.add('hidden');
      try {
        localStorage.setItem(DISMISS_KEY, '1');
      } catch (_) {}
    });
  }

  function refreshInstallBanner() {
    const banner = document.getElementById('installBanner');
    const msg = document.getElementById('installBannerText');
    if (!msg || !window.CR_I18N || banner?.classList.contains('hidden')) return;
    const key = isIos() ? 'pwa.installIos' : 'pwa.installGeneric';
    msg.textContent = window.CR_I18N.t(key);
  }

  registerServiceWorker();
  window.CR_PWA = { setupInstallBanner, refreshInstallBanner, isStandalone, isIos };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupInstallBanner);
  } else {
    setupInstallBanner();
  }
})();
