/* Django admin: a notice shortly before the idle sign-out (settings ADMIN_SESSION_IDLE_SECONDS, default 30 minutes).
   The server counts idle time from the last request to the admin, so the timer starts at page load and again after
   "Stay signed in" (one small request to the admin home page). Text is bilingual (English first). No data is sent. */
(function () {
  'use strict';
  var script = document.currentScript;
  if (!script || !script.src) return;
  var params = new URL(script.src, location.href).searchParams;
  var idle = parseInt(params.get('idle'), 10) || 1800;
  var ping = params.get('ping') || '/';
  var lead = idle > 600 ? 300 : Math.floor(idle / 2); // warn 5 minutes before (half the time for very short limits)
  var minutes = Math.max(1, Math.round(lead / 60));
  var timer = null;
  var box = null;

  function start() {
    clearTimeout(timer);
    timer = setTimeout(show, (idle - lead) * 1000);
  }

  function hide() {
    if (box) { box.remove(); box = null; }
  }

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (text) node.textContent = text;
    return node;
  }

  function show() {
    hide();
    box = el('div', { role: 'alert', style: 'position:fixed;inset-inline:1rem;bottom:1rem;z-index:99999;max-width:32rem;margin-inline:auto;padding:1rem;background:#fff7e6;color:#4a2f00;border:2px solid #b45309;border-radius:.5rem;font:16px/1.5 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.25)' });
    box.appendChild(el('p', { style: 'margin:0 0 .25rem' }, 'You will be signed out in about ' + minutes + ' minutes because of inactivity.'));
    box.appendChild(el('p', { dir: 'rtl', lang: 'ar', style: 'margin:0 0 .75rem' }, 'سيتم تسجيل خروجك بعد حوالي ' + minutes + ' دقائق بسبب عدم النشاط.'));
    var stay = el('button', { type: 'button', style: 'padding:.5rem 1rem;font-size:1rem;cursor:pointer' }, 'Stay signed in / ابقَ مسجّلًا');
    stay.addEventListener('click', keepAlive);
    box.appendChild(stay);
    document.body.appendChild(box);
    stay.focus();
  }

  function ended() {
    hide();
    box = el('div', { role: 'alert', style: 'position:fixed;inset-inline:1rem;bottom:1rem;z-index:99999;max-width:32rem;margin-inline:auto;padding:1rem;background:#fdecec;color:#7a1212;border:2px solid #9b1c1c;border-radius:.5rem;font:16px/1.5 system-ui,sans-serif' });
    box.appendChild(el('p', { style: 'margin:0' }, 'Your session ended. Reload the page to sign in again. / انتهت الجلسة. أعد تحميل الصفحة لتسجيل الدخول.'));
    document.body.appendChild(box);
  }

  function keepAlive() {
    fetch(ping, { credentials: 'same-origin', cache: 'no-store', headers: { 'X-Requested-With': 'idle-keepalive' } })
      .then(function (r) {
        if (!r.ok || r.redirected || /login/.test(r.url)) return ended();
        hide();
        start();
      })
      .catch(function () { ended(); });
  }

  function init() {
    if (document.getElementById('login-form')) return; // the sign-in page has no session to keep
    start();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
