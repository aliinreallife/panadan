/* Admin-only staging mirror status. Never confuse mirror health with live reports.
 * The endpoint returns aggregate numbers and timestamps, not customer data.
 * Render using textContent, never HTML from untrusted telemetry.
 */
(() => {
  'use strict';
  const panel = document.getElementById('mirror-health-panel');
  if (!panel) return;
  const el = id => document.getElementById(id);
  const fa = num => num === null || num === undefined ? '—' :
    new Intl.NumberFormat('fa-IR').format(num);
  const time = value => {
    if (!value) return '—';
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return '—';
    return new Intl.DateTimeFormat('fa-IR', {
      dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Tehran',
    }).format(date);
  };
  const delay = seconds => {
    if (!Number.isFinite(seconds) || seconds < 0) return '—';
    if (seconds < 60) return 'کمتر از یک دقیقه';
    if (seconds < 3600) return fa(Math.ceil(seconds / 60)) + ' دقیقه';
    if (seconds < 86400) return fa(Math.ceil(seconds / 3600)) + ' ساعت';
    return fa(Math.ceil(seconds / 86400)) + ' روز';
  };
  const states = {
    caught_up: ['به‌روز', 'ok'],
    catching_up: ['در حال جبران عقب‌ماندگی', 'syncing'],
    scheduled_idle: ['زمان‌بندی فعال · بین دو اجرا', 'muted'],
    behind: ['عقب‌مانده', 'warning'],
    vpn_down: ['اتصال VPN قطع است', 'warning'],
    paused: ['زمان‌بندی متوقف است', 'warning'],
    service_failed: ['خطا در همگام‌سازی', 'warning'],
    disk_low: ['فضای ذخیره‌سازی کم است', 'warning'],
    unavailable: ['اطلاعات همگام‌سازی در دسترس نیست', 'warning'],
    not_configured: ['همگام‌سازی محلی تنظیم نشده', 'muted'],
  };
  let busy = false;
  const show = data => {
    const [label, state] = states[data.state] || states.unavailable;
    const status = el('mirror-health-state');
    // Guarded ingestion is disabled *between* scheduled runs by design.
    // Never conflate the neutral scheduled interval with a missing publisher.
    const scheduledIdle = data.state === 'scheduled_idle' &&
      data.source_enabled === false && data.timer_active === true;
    const missing = data.state === 'not_configured';
    status.textContent = scheduledIdle ? 'زمان‌بندی فعال · بین دو اجرا' :
      missing ? 'اطلاعات پایش هنوز در دسترس نیست' : label;
    status.dataset.state = state;
    const explanation = el('mirror-health-explanation');
    if (explanation) {
      explanation.textContent = scheduledIdle ?
        'زمان‌بندی همگام‌سازی فعال است. سرویس در فاصلهٔ بین اجراها ورود داده را به‌صورت موقت می‌بندد؛ آخرین نقطهٔ ثبت‌شده تازه است. گزارش‌های اصلی پانادان مستقل از نسخهٔ محلی کار می‌کنند.' :
        missing ?
        'هنوز وضعیت قابل‌اعتمادی از سرویس پایش دریافت نشده است. اتصال فایل پایش و دسترسی خواندن آن را بررسی کنید.' :
        data.state === 'caught_up' ?
        'همگام‌سازی نسخهٔ محلی مطابق آخرین دادهٔ پایش به‌روز است؛ این وضعیت مستقل از مسیر گزارش‌های اصلی است.' :
        data.state === 'unavailable' ?
        'وضعیت همگام‌سازی قابل تأیید نیست. اطلاعات قدیمی یا نامعتبر به‌عنوان وضعیت سالم نمایش داده نمی‌شوند.' :
        data.state === 'behind' ?
        'آخرین بازهٔ همگام‌شده قدیمی‌تر از حد انتظار است. زمان‌بندی و گزارش آخرین اجرای سرویس را بررسی کنید.' :
        'وضعیت در حال تغییر است. جزئیات سرویس و زمان آخرین بررسی را در بخش پایین ببینید.';
    }
    el('mirror-health-records').textContent = fa(data.records);
    el('mirror-health-revisions').textContent = fa(data.revisions);
    el('mirror-health-through').textContent = time(data.completed_through);
    el('mirror-health-lag').textContent = delay(data.lag_seconds);
    const inProgress = data.state === 'catching_up';
    el('mirror-health-progress').hidden = !inProgress;
    el('mirror-health-processed').textContent = time(data.last_processed);
    el('mirror-health-upper').textContent = time(data.window_upper);
    el('mirror-health-vpn').textContent =
      data.vpn_healthy === true ? 'VPN: متصل' :
      data.vpn_healthy === false ? 'VPN: قطع' : 'VPN: نامشخص';
    el('mirror-health-timer').textContent =
      data.timer_active === true ? 'زمان‌بندی: فعال · هر ۵ دقیقه' :
      data.timer_active === false ? 'زمان‌بندی: متوقف' : 'زمان‌بندی: نامشخص';
    el('mirror-health-updated').textContent =
      'آخرین بررسی: ' + time(data.generated_at);
  };
  const load = async () => {
    if (busy) return;
    busy = true;
    try {
      const response = await fetch('/dashboard/mirror-health', {
        credentials: 'same-origin', cache: 'no-store',
        headers: {Accept: 'application/json'},
      });
      if (!response.ok) throw new Error('Unavailable mirror health');
      const data = await response.json();
      show(data);
    } catch (_error) {
      show({state: 'unavailable'});
    } finally {
      busy = false;
    }
  };
  el('mirror-health-refresh')?.addEventListener('click', load);
  load();
  window.setInterval(() => {
    if (document.visibilityState === 'visible') load();
  }, 60_000);
})();
