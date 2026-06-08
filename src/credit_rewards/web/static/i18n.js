(() => {
  const LEGACY_PREFIX = 'creditrewards_';
  const PREFIX = 'paycue_';
  try {
    for (let i = localStorage.length - 1; i >= 0; i -= 1) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith(LEGACY_PREFIX)) continue;
      const next = PREFIX + key.slice(LEGACY_PREFIX.length);
      if (localStorage.getItem(next) == null) {
        localStorage.setItem(next, localStorage.getItem(key));
      }
    }
  } catch (_) {}

  const LANG_KEY = 'paycue_lang_v1';
  const SUPPORTED = ['en', 'es', 'zh'];

  const MESSAGES = {
    en: {
      'app.title': 'PayCue — Which card?',
      'nav.recommend': 'Pick the best card',
      'nav.home': 'Back to home',
      'nav.settings': 'Wallet & settings',
      'nav.wallet': 'Wallet',
      'nav.walletBtn': 'Wallet · {count} cards',
      'lang.title': 'Choose your language',
      'lang.sub': 'You can change this later in My wallet.',
      'lang.en': 'English',
      'lang.es': 'Español',
      'lang.zh': '中文',
      'setup.title': 'Pick your cards',
      'setup.sub': 'Tap to add at least one card you carry.',
      'setup.start': 'Get started',
      'setup.errorMin': 'Select at least one card',
      'onboarding.step': 'Step {current} of {total}',
      'onboarding.skip': 'Skip tour',
      'onboarding.next': 'Next',
      'onboarding.finish': 'Start using PayCue',
      'onboarding.tryDemo': 'Try demo',
      'onboarding.replay': 'How to use PayCue',
      'onboarding.welcome.title': 'Welcome to PayCue',
      'onboarding.welcome.body':
        'At checkout, we tell you which card earns the most. No sign-up — your cards stay on this device only.',
      'onboarding.cards.title': 'Step 1 · Add your cards',
      'onboarding.cards.body':
        'Tap any cards you carry from the popular list. You need at least one.',
      'onboarding.search.title': 'Step 2 · Search by bank',
      'onboarding.search.body':
        'Co-brand cards (Hyatt, United, store cards)? Search the bank name — e.g. Chase, Amex, Citi.',
      'onboarding.save.title': 'Step 3 · Save & continue',
      'onboarding.save.body': 'When you are done picking cards, tap Get started.',
      'onboarding.payStore.title': 'Enter the store',
      'onboarding.payStore.body':
        'Type where you are shopping — in store or paste a website URL on the Website tab.',
      'onboarding.paySubmit.title': 'Get your recommendation',
      'onboarding.paySubmit.body':
        'Tap Recommend card. We rank your wallet and show estimated reward value in dollars.',
      'onboarding.payWallet.title': 'Wallet & settings',
      'onboarding.payWallet.body':
        'Add or remove cards anytime from the wallet icon. Language and data live here too.',
      'onboarding.done.title': 'You are ready',
      'onboarding.done.body':
        'Try a store like Chipotle or Walmart. Amount is optional — we compare categories either way.',
      'pay.title': 'Which card to use?',
      'pay.sub': 'Enter a store — we pick the best card from your {count} cards.',
      'pay.tabOnline': 'Website',
      'pay.tabStore': 'In store',
      'pay.urlLabel': 'Checkout / store URL',
      'pay.urlPlaceholder': 'walmart.com, nike.com…',
      'pay.urlHint': 'Paste a URL for online shopping rewards (unknown sites default to Online Shopping).',
      'pay.nearbyLabel': 'Nearby stores (GPS)',
      'pay.nearbyLoading': 'Finding nearby stores…',
      'pay.storeLabel': 'Store name',
      'pay.storePlaceholder': 'Walmart, Nike, Central Market…',
      'pay.storeHint': 'Store name for in-store rewards (GPS improves matching).',
      'pay.amountLabel': 'Amount (USD, optional)',
      'pay.amountPlaceholder': '100',
      'pay.amountHint': 'For reward $ estimates. Leave blank to compare by category only.',
      'pay.amountEstimateNote': 'Estimates based on ${amount} purchase',
      'pay.submit': 'Recommend card',
      'pay.submitting': 'Finding best card…',
      'pay.useLast': '↳ {name}',
      'pay.lastMerchant': 'Last purchase',
      'pay.errorUrl': 'Paste a checkout URL',
      'pay.errorStore': 'Enter a store name',
      'pay.errorNoCards': 'Add at least one card first',
      'pay.errorRequest': 'Request failed',
      'loc.online': 'Website mode: online shopping rewards',
      'loc.storeOk': 'In-store mode: using GPS for nearby stores',
      'loc.storeWarn': 'Allow location for nearby stores',
      'result.heroLabel': 'Use this card',
      'result.pointsValue': '{points} pts ≈ ${amount}',
      'result.cashValue': '{pct}% cash back ≈ ${amount}',
      'result.rankPoints': '{points} pts · ${amount}',
      'result.rankCash': '${amount} cash back',
      'result.value': '≈ ${amount} reward value',
      'result.rankHead': 'Your {count} cards ranked',
      'result.rankPartnerEarn': '{mult}× partner earn · {pts} pts',
      'result.partnerBadge': 'Partner earn',
      'result.partnerRankNote':
        'Your {card} still earns {mult}× at {merchant} ({pts} pts). Ranked #{rank} because another card has a higher estimated $ value on this purchase.',
      'result.valuationHelp': 'How we estimate $',
      'result.valuationTitle': 'How we estimate $',
      'result.valuationIntro': 'We show one estimated dollar value so you can compare cards at checkout.',
      'result.valuationPoints': 'Points cards: points earned × official cents-per-point (CPP). Example: 400 pts × 2.2¢ ≈ $8.80.',
      'result.valuationPartner':
        "At a partner store (e.g. delta.com), we value that brand's points at typical in-brand redemption rates—so your co-brand card's earn shows fairly in $.",
      'result.valuationCash': 'Cash-back cards: purchase × earn rate. Example: $100 × 6% = $6.00 cash back.',
      'result.valuationNote': 'Not guaranteed cash. Redemption value varies by how you use rewards.',
      'result.valuationClose': 'Got it',
      'savings.bannerMonth': "This month you've saved ~${amount} in rewards",
      'savings.bannerTimes': '{count} times',
      'savings.bannerHint': 'Tap to review',
      'savings.resultAdded': '~${amount} saved · ~${monthTotal} this month',
      'savings.sectionTitle': "Rewards you've saved",
      'savings.viewHistory': 'View history',
      'savings.historyTitle': 'Rewards history',
      'savings.historySub': 'Remove entries that were just checks — totals update right away.',
      'savings.historyEmpty': 'No saved rewards yet.',
      'savings.removeSelected': 'Remove selected',
      'savings.historyRowReward': '~${amount} saved',
      'savings.historyRowEst': 'est. ${amount} purchase',
      'savings.month': 'This month',
      'savings.quarter': 'This quarter',
      'savings.allTime': 'All time',
      'savings.times': '{count} times',
      'savings.disclaimer': 'Estimated from your picks. Blank amounts assume ${default}.',
      'wallet.title': 'My wallet',
      'wallet.sub': 'Your cards, language, and data on this device.',
      'wallet.sectionCards': 'Your cards',
      'wallet.sectionAdd': 'Add a card',
      'wallet.sectionApp': 'App settings',
      'wallet.remove': 'Remove',
      'wallet.popular': 'Popular cards',
      'wallet.missing': "Don't see your card?",
      'wallet.issuerLabel': 'Bank name (e.g. Chase, Amex, Citi)',
      'wallet.issuerPlaceholder': 'Chase',
      'wallet.search': 'Search',
      'wallet.back': 'Back',
      'wallet.reset': 'Clear all data…',
      'reset.title': 'Clear all data?',
      'reset.lead': 'This removes your cards, saved rewards, and settings from this device. This cannot be undone.',
      'reset.confirm': 'Clear everything',
      'reset.cancel': 'Cancel',
      'wallet.language': 'Language',
      'wallet.errorMin': 'Keep at least one card',
      'wallet.errorIssuerLen': 'Enter at least 2 characters for bank name',
      'wallet.searching': 'Searching…',
      'wallet.noIssuerMatch': 'No cards found — try Chase, American Express, etc.',
      'modal.title': 'Confirm store',
      'modal.lead': 'Is this the right store? We will pick your best card.',
      'modal.confirm': 'Confirm & recommend',
      'modal.cancel': 'Go back',
      'modal.online': ' (online)',
      'modal.inStore': ' (in store)',
      'conf.high': 'High confidence',
      'conf.medium': 'Medium — please verify',
      'conf.low': 'Low — verify carefully',
      'pwa.installIos': 'Install: tap Share ↑ then "Add to Home Screen".',
      'pwa.installGeneric': 'Add to Home Screen for a full-screen app experience.',
      'pwa.dismiss': 'Dismiss install tip',
    },
    es: {
      'app.title': 'PayCue — ¿Qué tarjeta?',
      'nav.recommend': 'Elige la mejor tarjeta',
      'nav.home': 'Volver al inicio',
      'nav.settings': 'Cartera y ajustes',
      'nav.wallet': 'Cartera',
      'nav.walletBtn': 'Cartera · {count} tarjetas',
      'lang.title': 'Elige tu idioma',
      'lang.sub': 'Puedes cambiarlo después en Mi cartera.',
      'lang.en': 'English',
      'lang.es': 'Español',
      'lang.zh': '中文',
      'setup.title': 'Elige tus tarjetas',
      'setup.sub': 'Toca para añadir al menos una tarjeta.',
      'setup.start': 'Empezar',
      'setup.errorMin': 'Selecciona al menos una tarjeta',
      'onboarding.step': 'Paso {current} de {total}',
      'onboarding.skip': 'Saltar tour',
      'onboarding.next': 'Siguiente',
      'onboarding.finish': 'Empezar con PayCue',
      'onboarding.tryDemo': 'Probar demo',
      'onboarding.replay': 'Cómo usar PayCue',
      'onboarding.welcome.title': 'Bienvenido a PayCue',
      'onboarding.welcome.body':
        'En la caja te decimos qué tarjeta rinde más. Sin registro — tus tarjetas quedan solo en este dispositivo.',
      'onboarding.cards.title': 'Paso 1 · Añade tus tarjetas',
      'onboarding.cards.body': 'Toca las tarjetas que usas. Necesitas al menos una.',
      'onboarding.search.title': 'Paso 2 · Busca por banco',
      'onboarding.search.body':
        '¿Tarjetas co-brand (Hyatt, United)? Busca el banco — p. ej. Chase, Amex, Citi.',
      'onboarding.save.title': 'Paso 3 · Guardar y continuar',
      'onboarding.save.body': 'Cuando termines, pulsa Empezar.',
      'onboarding.payStore.title': 'Indica la tienda',
      'onboarding.payStore.body':
        'Escribe dónde compras — en tienda o pega la URL en la pestaña Sitio web.',
      'onboarding.paySubmit.title': 'Obtén la recomendación',
      'onboarding.paySubmit.body':
        'Pulsa Recomendar tarjeta. Ordenamos tu cartera y mostramos el valor estimado en $.',
      'onboarding.payWallet.title': 'Cartera y ajustes',
      'onboarding.payWallet.body':
        'Añade o quita tarjetas desde el icono de cartera. Idioma y datos también ahí.',
      'onboarding.done.title': 'Listo',
      'onboarding.done.body':
        'Prueba con Chipotle o Walmart. El importe es opcional — comparamos por categoría igualmente.',
      'pay.title': '¿Qué tarjeta usar?',
      'pay.sub': 'Indica la tienda — elegimos la mejor de tus {count} tarjetas.',
      'pay.tabOnline': 'Sitio web',
      'pay.tabStore': 'Tienda física',
      'pay.urlLabel': 'URL de pago / tienda',
      'pay.urlPlaceholder': 'walmart.com, nike.com…',
      'pay.urlHint': 'Pega la URL para recompensas en línea (sitios desconocidos: Online Shopping).',
      'pay.nearbyLabel': 'Tiendas cercanas (GPS)',
      'pay.nearbyLoading': 'Buscando tiendas cercanas…',
      'pay.storeLabel': 'Nombre de la tienda',
      'pay.storePlaceholder': 'Walmart, Nike, Central Market…',
      'pay.storeHint': 'Nombre para recompensas en tienda (GPS mejora la coincidencia).',
      'pay.amountLabel': 'Monto (USD, opcional)',
      'pay.amountPlaceholder': '100',
      'pay.amountHint': 'Para estimar recompensas en $. Déjalo vacío para comparar solo por categoría.',
      'pay.amountEstimateNote': 'Estimaciones con compra de ${amount}',
      'pay.submit': 'Recomendar tarjeta',
      'pay.submitting': 'Buscando la mejor tarjeta…',
      'pay.useLast': '↳ {name}',
      'pay.lastMerchant': 'Última compra',
      'pay.errorUrl': 'Pega la URL de pago',
      'pay.errorStore': 'Ingresa el nombre de la tienda',
      'pay.errorNoCards': 'Añade al menos una tarjeta',
      'pay.errorRequest': 'Error en la solicitud',
      'loc.online': 'Modo web: recompensas de compras en línea',
      'loc.storeOk': 'Modo tienda: GPS activo para tiendas cercanas',
      'loc.storeWarn': 'Modo tienda: permite ubicación para tiendas cercanas',
      'result.heroLabel': 'Usa esta tarjeta',
      'result.pointsValue': '{points} pts ≈ ${amount}',
      'result.cashValue': '{pct}% cashback ≈ ${amount}',
      'result.rankPoints': '{points} pts · ${amount}',
      'result.rankCash': '${amount} cashback',
      'result.value': '≈ ${amount} valor en recompensas',
      'result.rankHead': 'Ranking de tus {count} tarjetas',
      'result.rankPartnerEarn': '{mult}× bonus socio · {pts} pts',
      'result.partnerBadge': 'Bonus socio',
      'result.partnerRankNote':
        'Tu {card} sigue ganando {mult}× en {merchant} ({pts} pts). Puesto #{rank} porque otra tarjeta tiene mayor $ estimado en esta compra.',
      'result.valuationHelp': 'Cómo estimamos $',
      'result.valuationTitle': 'Cómo estimamos $',
      'result.valuationIntro': 'Mostramos un valor en dólares para comparar tarjetas al pagar.',
      'result.valuationPoints': 'Tarjetas de puntos: puntos × centavos por punto (CPP). Ej.: 400 pts × 2.2¢ ≈ $8.80.',
      'result.valuationPartner':
        'En tiendas asociadas (p. ej. delta.com), valoramos los puntos de esa marca según canje típico en la marca.',
      'result.valuationCash': 'Cashback: compra × tasa. Ej.: $100 × 6% = $6.00.',
      'result.valuationNote': 'No es efectivo garantizado. El valor real depende de cómo canjees.',
      'result.valuationClose': 'Entendido',
      'savings.bannerMonth': 'Este mes has ahorrado ~${amount} en recompensas',
      'savings.bannerTimes': '{count} veces',
      'savings.bannerHint': 'Toca para revisar',
      'savings.resultAdded': '~${amount} ahorrado · ~${monthTotal} este mes',
      'savings.sectionTitle': 'Recompensas ahorradas',
      'savings.viewHistory': 'Ver historial',
      'savings.historyTitle': 'Historial de recompensas',
      'savings.historySub': 'Quita entradas que fueron solo pruebas — los totales se actualizan al instante.',
      'savings.historyEmpty': 'Aún no hay recompensas guardadas.',
      'savings.removeSelected': 'Eliminar seleccionados',
      'savings.historyRowReward': '~${amount} ahorrado',
      'savings.historyRowEst': 'est. compra ${amount}',
      'savings.month': 'Este mes',
      'savings.quarter': 'Este trimestre',
      'savings.allTime': 'Total',
      'savings.times': '{count} veces',
      'savings.disclaimer': 'Estimado según tus elecciones. Montos vacíos asumen ${default}.',
      'wallet.title': 'Mi cartera',
      'wallet.sub': 'Tus tarjetas, idioma y datos en este dispositivo.',
      'wallet.sectionCards': 'Tus tarjetas',
      'wallet.sectionAdd': 'Añadir tarjeta',
      'wallet.sectionApp': 'Ajustes de la app',
      'wallet.remove': 'Quitar',
      'wallet.popular': 'Tarjetas populares',
      'wallet.missing': '¿No ves tu tarjeta?',
      'wallet.issuerLabel': 'Banco (ej. Chase, Amex, Citi)',
      'wallet.issuerPlaceholder': 'Chase',
      'wallet.search': 'Buscar',
      'wallet.back': 'Volver',
      'wallet.reset': 'Borrar todos los datos…',
      'reset.title': '¿Borrar todos los datos?',
      'reset.lead': 'Se eliminarán tus tarjetas, recompensas guardadas y ajustes en este dispositivo. No se puede deshacer.',
      'reset.confirm': 'Borrar todo',
      'reset.cancel': 'Cancelar',
      'wallet.language': 'Idioma',
      'wallet.errorMin': 'Conserva al menos una tarjeta',
      'wallet.errorIssuerLen': 'Ingresa al menos 2 caracteres del banco',
      'wallet.searching': 'Buscando…',
      'wallet.noIssuerMatch': 'Sin resultados — prueba Chase, American Express, etc.',
      'modal.title': 'Confirmar tienda',
      'modal.lead': '¿Es la tienda correcta? Elegiremos tu mejor tarjeta.',
      'modal.confirm': 'Confirmar y recomendar',
      'modal.cancel': 'Volver',
      'modal.online': ' (en línea)',
      'modal.inStore': ' (tienda)',
      'conf.high': 'Alta confianza',
      'conf.medium': 'Media — verifica',
      'conf.low': 'Baja — verifica con cuidado',
      'pwa.installIos': 'Instalar: toca Compartir ↑ y luego «Añadir a pantalla de inicio».',
      'pwa.installGeneric': 'Añade a la pantalla de inicio para usar la app a pantalla completa.',
      'pwa.dismiss': 'Cerrar consejo de instalación',
    },
    zh: {
      'app.title': 'PayCue — 用哪张卡？',
      'nav.recommend': '选出最优卡',
      'nav.home': '回到主页',
      'nav.settings': '钱包与设置',
      'nav.wallet': '钱包',
      'nav.walletBtn': '钱包 · {count} 张卡',
      'lang.title': '选择语言',
      'lang.sub': '之后可在「我的钱包」里更改。',
      'lang.en': 'English',
      'lang.es': 'Español',
      'lang.zh': '中文',
      'setup.title': '选择你的卡',
      'setup.sub': '轻点卡片添加，至少选 1 张。',
      'setup.start': '开始用',
      'setup.errorMin': '请至少选择一张卡',
      'onboarding.step': '第 {current} / {total} 步',
      'onboarding.skip': '跳过引导',
      'onboarding.next': '下一步',
      'onboarding.finish': '开始使用 PayCue',
      'onboarding.tryDemo': '体验一下',
      'onboarding.replay': '使用说明',
      'onboarding.welcome.title': '欢迎使用 PayCue',
      'onboarding.welcome.body':
        '结账时帮你选回报最高的卡。无需注册，卡包只保存在本机。',
      'onboarding.cards.title': '第 1 步 · 添加你的卡',
      'onboarding.cards.body': '从热门列表点选你常用的卡，至少选 1 张。',
      'onboarding.search.title': '第 2 步 · 按银行搜索',
      'onboarding.search.body':
        '联名卡（Hyatt、United 等）？搜银行名即可，如 Chase、Amex、Citi。',
      'onboarding.save.title': '第 3 步 · 保存并继续',
      'onboarding.save.body': '选好后点「开始用」。',
      'onboarding.payStore.title': '输入商家',
      'onboarding.payStore.body':
        '填写购物地点；网购可切到「网站」粘贴结账链接。',
      'onboarding.paySubmit.title': '获取推荐',
      'onboarding.paySubmit.body':
        '点「推荐用卡」，我们会排序并显示预估回报（美元）。',
      'onboarding.payWallet.title': '卡包与设置',
      'onboarding.payWallet.body':
        '右上角卡包可随时增删卡、改语言或清除数据。',
      'onboarding.done.title': '可以开始了',
      'onboarding.done.body':
        '试试 Chipotle 或 Walmart。金额可留空，我们仍按消费类别比较。',
      'pay.title': '这次用哪张卡？',
      'pay.sub': '输入店家，在你 {count} 张卡里找出最优的一张。',
      'pay.tabOnline': '网站',
      'pay.tabStore': '实体店',
      'pay.urlLabel': '结账页 / 官网 URL',
      'pay.urlPlaceholder': 'walmart.com、nike.com 等',
      'pay.urlHint': '粘贴网址 → 按网购 reward 分类（未知网站默认 Online Shopping）。',
      'pay.nearbyLabel': '附近门店（基于定位）',
      'pay.nearbyLoading': '查找附近门店…',
      'pay.storeLabel': '实体店名',
      'pay.storePlaceholder': 'Walmart, Nike, Central Market…',
      'pay.storeHint': '输入店名 → 按实体店 reward 分类（可定位 Google Maps）。',
      'pay.amountLabel': '消费金额 (USD，可选)',
      'pay.amountPlaceholder': '100',
      'pay.amountHint': '用于估算 reward 美元价值。留空则仅按消费类别比较。',
      'pay.amountEstimateNote': '以下按 ${amount} 消费估算',
      'pay.submit': '推荐卡',
      'pay.submitting': '正在选最优卡…',
      'pay.useLast': '↳ {name}',
      'pay.lastMerchant': '上次商家',
      'pay.errorUrl': '请粘贴结账页 URL',
      'pay.errorStore': '请输入店名',
      'pay.errorNoCards': '请先添加至少一张卡',
      'pay.errorRequest': '请求失败',
      'loc.online': '网站模式：按网购 reward 分类',
      'loc.storeOk': '实体店模式：已通过 Google Maps 匹配附近门店',
      'loc.storeWarn': '实体店模式：请允许定位，以便匹配附近门店',
      'result.heroLabel': '推荐使用',
      'result.pointsValue': '{points} 分 ≈ ${amount}',
      'result.cashValue': '{pct}% 返现 ≈ ${amount}',
      'result.rankPoints': '{points} 分 · ${amount}',
      'result.rankCash': '${amount} 返现',
      'result.value': '≈ ${amount} reward 价值',
      'result.rankHead': '钱包 {count} 张卡排名',
      'result.rankPartnerEarn': '合作商户 {mult}× · {pts} 分',
      'result.partnerBadge': '联名奖励',
      'result.partnerRankNote':
        '你的 {card} 在此仍享 {mult}×（{pts} 分）。按预估 $ 排第 {rank}，因另一张卡在本笔消费上估值更高。',
      'result.valuationHelp': '如何估算 $',
      'result.valuationTitle': '如何估算 $',
      'result.valuationIntro': '结账时用一个美元估值帮你比较各卡。',
      'result.valuationPoints': '积分卡：积分 × 官方 CPP（分/点）。例：400 分 × 2.2¢ ≈ $8.80。',
      'result.valuationPartner':
        '在合作商户（如 delta.com）消费时，我们按该品牌常见兑换率估算积分，联名卡的回报会体现在 $ 估值中。',
      'result.valuationCash': '返现卡：消费 × 返现比例。例：$100 × 6% = $6.00。',
      'result.valuationNote': '非保证兑现；实际价值取决于兑换方式。',
      'result.valuationClose': '知道了',
      'savings.bannerMonth': '本月已帮你省下 ~${amount} reward',
      'savings.bannerTimes': '{count} 次',
      'savings.bannerHint': '点击查看',
      'savings.resultAdded': '又省下 ~${amount} · 本月 ~${monthTotal}',
      'savings.sectionTitle': '已省 reward',
      'savings.viewHistory': '查看记录',
      'savings.historyTitle': 'Reward 记录',
      'savings.historySub': '只是查一下、没真正消费？勾选后删除，累计会立刻更新。',
      'savings.historyEmpty': '还没有记录。',
      'savings.removeSelected': '删除所选',
      'savings.historyRowReward': '~${amount} 已省',
      'savings.historyRowEst': '按 ${amount} 消费估算',
      'savings.month': '本月',
      'savings.quarter': '本季度',
      'savings.allTime': '全部',
      'savings.times': '{count} 次',
      'savings.disclaimer': '根据你的选卡估算。未填金额按 ${default} 计。',
      'wallet.title': '我的钱包',
      'wallet.sub': '本机的卡片、语言与数据。',
      'wallet.sectionCards': '我的卡',
      'wallet.sectionAdd': '添加卡片',
      'wallet.sectionApp': '应用设置',
      'wallet.remove': '移除',
      'wallet.popular': '热门卡',
      'wallet.missing': '找不到你的卡？',
      'wallet.issuerLabel': '输入发卡行（如 Chase、Amex、Citi）',
      'wallet.issuerPlaceholder': 'Chase',
      'wallet.search': '查找',
      'wallet.back': '返回',
      'wallet.reset': '清除全部数据…',
      'reset.title': '清除全部数据？',
      'reset.lead': '将删除本机的卡片、已省 reward 记录和设置，且无法恢复。',
      'reset.confirm': '确认清除',
      'reset.cancel': '取消',
      'wallet.language': '语言',
      'wallet.errorMin': '至少保留一张卡',
      'wallet.errorIssuerLen': '请输入至少 2 个字符的发卡行名称',
      'wallet.searching': '查找中…',
      'wallet.noIssuerMatch': '未找到该发卡行的卡，请换关键词（如 Chase、American Express）',
      'modal.title': '确认商家',
      'modal.lead': '这家店对吗？确认后帮你选最优卡。',
      'modal.confirm': '确认，推荐最优卡',
      'modal.cancel': '返回修改',
      'modal.online': '（网站）',
      'modal.inStore': '（实体店）',
      'conf.high': '高置信度',
      'conf.medium': '中置信度 — 请核对',
      'conf.low': '低置信度 — 请仔细核对',
      'pwa.installIos': '安装：点 Safari 分享 ↑，再选「添加到主屏幕」。',
      'pwa.installGeneric': '添加到主屏幕，获得全屏 App 体验。',
      'pwa.dismiss': '关闭安装提示',
    },
  };

  const HTML_LANG = { en: 'en', es: 'es', zh: 'zh-Hans' };

  let locale = 'en';

  function interpolate(text, vars) {
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] != null ? String(vars[k]) : `{${k}}`));
  }

  function t(key, vars) {
    const bag = MESSAGES[locale] || MESSAGES.en;
    const fallback = MESSAGES.en[key] || key;
    return interpolate(bag[key] || fallback, vars);
  }

  function detectDefaultLocale() {
    const nav = (navigator.language || 'en').toLowerCase();
    if (nav.startsWith('zh')) return 'zh';
    if (nav.startsWith('es')) return 'es';
    return 'en';
  }

  function loadLocale() {
    try {
      const saved = localStorage.getItem(LANG_KEY);
      if (saved && SUPPORTED.includes(saved)) return saved;
    } catch (_) {}
    return null;
  }

  function saveLocale(code) {
    localStorage.setItem(LANG_KEY, code);
    locale = code;
  }

  function setLocale(code) {
    if (!SUPPORTED.includes(code)) code = 'en';
    saveLocale(code);
    document.documentElement.lang = HTML_LANG[code] || 'en';
    document.title = t('app.title');
    apply(document);
  }

  function apply(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-i18n]').forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    scope.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    scope.querySelectorAll('[data-i18n-title]').forEach((el) => {
      document.title = t(el.dataset.i18nTitle);
    });
    scope.querySelectorAll('[data-i18n-aria]').forEach((el) => {
      const label = t(el.dataset.i18nAria);
      el.setAttribute('aria-label', label);
      if (el.hasAttribute('title')) el.title = label;
    });
  }

  function hasChosenLocale() {
    return Boolean(loadLocale());
  }

  window.CR_I18N = {
    SUPPORTED,
    t,
    apply,
    setLocale,
    loadLocale,
    saveLocale,
    hasChosenLocale,
    detectDefaultLocale,
    get locale() {
      return locale;
    },
    init() {
      const saved = loadLocale();
      locale = saved || detectDefaultLocale();
      if (saved) {
        document.documentElement.lang = HTML_LANG[locale] || 'en';
        document.title = t('app.title');
      }
    },
  };

  window.CR_I18N.init();
})();
