(() => {
  const STORAGE_KEY = 'paycue_onboarding_v1';

  const SETUP_STEPS = ['welcome', 'cards', 'search', 'save'];
  const PAY_STEPS = ['payStore', 'paySubmit', 'payWallet', 'done'];

  let phase = null;
  let stepIndex = 0;
  let tryDemoFn = null;
  let onCompleteFn = null;

  function t(key, vars) {
    return window.CR_I18N?.t(key, vars) ?? key;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function isComplete() {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'done';
    } catch {
      return false;
    }
  }

  function markComplete() {
    try {
      localStorage.setItem(STORAGE_KEY, 'done');
    } catch (_) {}
    hide();
    window.CR_ANALYTICS?.track('onboarding_complete', { phase: phase || 'all' });
    onCompleteFn?.();
  }

  function reset() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (_) {}
  }

  function stepsForPhase(name) {
    return name === 'pay' ? PAY_STEPS : SETUP_STEPS;
  }

  function currentStepId() {
    return stepsForPhase(phase)[stepIndex];
  }

  function hide() {
    const root = $('onboardingTour');
    root?.classList.add('hidden');
    root?.setAttribute('aria-hidden', 'true');
    $('onboardingSpotlight')?.setAttribute('hidden', '');
    document.body.classList.remove('onboarding-active');
  }

  function showRoot() {
    const root = $('onboardingTour');
    root?.classList.remove('hidden');
    root?.setAttribute('aria-hidden', 'false');
    document.body.classList.add('onboarding-active');
  }

  function positionSpotlight(target) {
    const spot = $('onboardingSpotlight');
    if (!spot || !target) {
      spot?.setAttribute('hidden', '');
      return;
    }
    const r = target.getBoundingClientRect();
    const pad = 8;
    spot.removeAttribute('hidden');
    spot.style.top = `${Math.max(0, r.top - pad)}px`;
    spot.style.left = `${Math.max(0, r.left - pad)}px`;
    spot.style.width = `${Math.min(window.innerWidth, r.width + pad * 2)}px`;
    spot.style.height = `${Math.min(window.innerHeight, r.height + pad * 2)}px`;
  }

  function targetForStep(stepId) {
    const map = {
      cards: '#localCardPicker',
      search: '.setup-add-section',
      save: '#localSave',
      payStore: '#merchantName',
      paySubmit: '#go',
      payWallet: '#btnWalletSettings',
    };
    const sel = map[stepId];
    return sel ? document.querySelector(sel) : null;
  }

  function renderStep() {
    const stepId = currentStepId();
    const steps = stepsForPhase(phase);
    const titleEl = $('onboardingTitle');
    const bodyEl = $('onboardingBody');
    const stepEl = $('onboardingStep');
    const nextBtn = $('onboardingNext');
    const skipBtn = $('onboardingSkip');
    const demoBtn = $('onboardingDemo');

    if (stepEl) {
      stepEl.textContent = t('onboarding.step', { current: stepIndex + 1, total: steps.length });
    }
    if (titleEl) titleEl.textContent = t(`onboarding.${stepId}.title`);
    if (bodyEl) bodyEl.textContent = t(`onboarding.${stepId}.body`);

    const isWelcome = stepId === 'welcome';
    const isDone = stepId === 'done';
    if (demoBtn) {
      demoBtn.hidden = !isWelcome || !tryDemoFn;
      demoBtn.textContent = t('onboarding.tryDemo');
    }
    if (nextBtn) {
      nextBtn.textContent = isDone ? t('onboarding.finish') : t('onboarding.next');
    }
    if (skipBtn) skipBtn.textContent = t('onboarding.skip');

    const target = targetForStep(stepId);
    if (target) {
      target.scrollIntoView({ block: 'center', behavior: 'smooth' });
      requestAnimationFrame(() => positionSpotlight(target));
    } else {
      positionSpotlight(null);
    }
  }

  function next() {
    const steps = stepsForPhase(phase);
    if (stepIndex >= steps.length - 1) {
      if (phase === 'setup') {
        hide();
        return;
      }
      markComplete();
      return;
    }
    stepIndex += 1;
    renderStep();
  }

  function skip() {
    window.CR_ANALYTICS?.track('onboarding_skip', { phase, step: currentStepId() });
    markComplete();
  }

  async function tryDemo() {
    if (!tryDemoFn) return;
    window.CR_ANALYTICS?.track('onboarding_try_demo');
    hide();
    await tryDemoFn();
    markComplete();
  }

  function start(name, { force = false } = {}) {
    if (!force && isComplete()) return false;
    phase = name;
    stepIndex = 0;
    showRoot();
    renderStep();
    window.CR_ANALYTICS?.track('onboarding_start', { phase: name });
    return true;
  }

  function startPayTour({ force = false } = {}) {
    if (!force && isComplete()) return false;
    phase = 'pay';
    stepIndex = 0;
    showRoot();
    renderStep();
    window.CR_ANALYTICS?.track('onboarding_start', { phase: 'pay' });
    return true;
  }

  function bind() {
    $('onboardingNext')?.addEventListener('click', () => next());
    $('onboardingSkip')?.addEventListener('click', () => skip());
    $('onboardingDemo')?.addEventListener('click', () => void tryDemo());
    $('onboardingBackdrop')?.addEventListener('click', () => skip());

    window.addEventListener('resize', () => {
      if ($('onboardingTour')?.classList.contains('hidden')) return;
      positionSpotlight(targetForStep(currentStepId()));
    });
  }

  window.CR_ONBOARDING = {
    bind,
    start,
    startPayTour,
    isComplete,
    markComplete,
    reset,
    registerTryDemo(fn) {
      tryDemoFn = fn;
    },
    onComplete(fn) {
      onCompleteFn = fn;
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
