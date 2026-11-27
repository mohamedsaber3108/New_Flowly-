/* Flowly account portal: login, register, password reset, dashboard, requests, profile.
   Plain JS, no build step. All text is inserted with textContent (no HTML injection).
   Language and theme are shared with the main site through the same localStorage keys
   (flowly-language, flowly-theme), so a visitor who browses in Arabic gets an Arabic, RTL portal. */
(function () {
  'use strict';
  var API = '/api/v1';
  var app = document.getElementById('app');
  var nav = document.getElementById('nav');
  var tools = document.getElementById('tools');
  var GOOGLE = document.body.getAttribute('data-google') === '1';
  var store = {
    get access() { return localStorage.getItem('flowly-access'); },
    get refresh() { return localStorage.getItem('flowly-refresh'); },
    set: function (a, r) { localStorage.setItem('flowly-access', a); if (r) localStorage.setItem('flowly-refresh', r); },
    clear: function () { localStorage.removeItem('flowly-access'); localStorage.removeItem('flowly-refresh'); }
  };
  var me = null;
  var currentRoute = 'login';

  // ------------------------------------------------------------------ i18n
  var AR = {
    'Sign in': 'تسجيل الدخول', 'Create account': 'إنشاء حساب', 'Dashboard': 'لوحة التحكم', 'My requests': 'طلباتي',
    'Profile': 'الملف الشخصي', 'Sign out': 'تسجيل الخروج', 'Email': 'البريد الإلكتروني', 'Password': 'كلمة المرور',
    'Forgot your password?': 'نسيت كلمة المرور؟', 'Create an account': 'أنشئ حسابًا', 'Continue with Google': 'المتابعة بحساب Google',
    'Create your account': 'أنشئ حسابك', 'First name': 'الاسم الأول', 'Last name': 'اسم العائلة',
    'Password (8+ characters)': 'كلمة المرور (٨ أحرف على الأقل)', 'Confirm password': 'تأكيد كلمة المرور',
    'I already have an account': 'لدي حساب بالفعل', 'Reset your password': 'إعادة تعيين كلمة المرور', 'Send reset link': 'أرسل رابط إعادة التعيين',
    'Back to sign in': 'العودة لتسجيل الدخول', 'Loading…': 'جارٍ التحميل…', 'Total requests': 'إجمالي الطلبات', 'Open': 'مفتوحة',
    'No upcoming consultation': 'لا توجد استشارة قادمة', 'Next consultation': 'الاستشارة القادمة', 'Cairo': 'بتوقيت القاهرة',
    'Reference': 'رقم الطلب', 'Type': 'النوع', 'Status': 'الحالة', 'Submitted': 'تاريخ الإرسال', 'Organization': 'المؤسسة',
    'No requests yet. Submit one from the Flowly site and it will appear here.': 'لا توجد طلبات بعد. أرسل طلبًا من موقع Flowly وسيظهر هنا.',
    'No requests yet.': 'لا توجد طلبات بعد.', 'Welcome': 'أهلًا', 'Your email is not verified yet.': 'لم يتم تأكيد بريدك الإلكتروني بعد.',
    'Recent requests': 'أحدث الطلبات', 'Request a consultation': 'اطلب استشارة', 'Team': 'الفريق',
    'Manage requests in the admin site or the /team console.': 'أدِر الطلبات من لوحة الإدارة أو صفحة الفريق.',
    'Open /team console': 'افتح صفحة الفريق', '← All requests': '→ كل الطلبات', 'Consultation': 'الاستشارة', 'None': 'لا يوجد',
    'Timeline': 'سجل الطلب', 'Save profile': 'حفظ الملف', 'Avatar': 'الصورة الشخصية', 'Avatar image (JPEG, PNG, WebP, GIF)': 'الصورة (JPEG أو PNG أو WebP أو GIF)',
    'Upload avatar': 'رفع الصورة', 'Choose an image first.': 'اختر صورة أولًا.', 'Change password': 'تغيير كلمة المرور',
    'Current password': 'كلمة المرور الحالية', 'New password': 'كلمة المرور الجديدة', 'Delete account': 'حذف الحساب',
    'Enter your password to confirm': 'أدخل كلمة المرور للتأكيد', 'Your account is disabled. Request history is kept for audit.': 'يتم تعطيل حسابك، ويُحتفظ بسجل الطلبات للمراجعة.',
    'Delete your account? You will be signed out and cannot sign in again.': 'هل تريد حذف حسابك؟ سيتم تسجيل خروجك ولن تتمكن من الدخول مرة أخرى.',
    'Role': 'الدور', 'email verified': 'البريد مؤكد', 'email not verified': 'البريد غير مؤكد', 'Your avatar': 'صورتك',
    'Email verified. You can sign in now.': 'تم تأكيد بريدك. يمكنك تسجيل الدخول الآن.',
    'That verification link is invalid or expired. Request a new one by signing in.': 'رابط التأكيد غير صالح أو منتهي. سجّل الدخول لطلب رابط جديد.',
    'Google sign-in did not complete. Please try again.': 'لم يكتمل تسجيل الدخول بحساب Google. حاول مرة أخرى.',
    'We sent a new verification link.': 'أرسلنا رابط تأكيد جديدًا.', 'Something went wrong.': 'حدث خطأ ما.',
    'Session expired. Please sign in again.': 'انتهت الجلسة. سجّل الدخول مرة أخرى.', 'Request failed.': 'تعذّر تنفيذ الطلب.',
    'Account created. Check your email to verify your address.': 'تم إنشاء الحساب. افتح بريدك لتأكيد العنوان.',
    'Account created. You can sign in now.': 'تم إنشاء الحساب. يمكنك تسجيل الدخول الآن.',
    'If an account exists for this email, a reset link was sent.': 'إذا كان هناك حساب بهذا البريد، فقد أرسلنا رابط إعادة التعيين.',
    'Profile updated.': 'تم تحديث الملف.', 'Profile updated. Verify your new email address.': 'تم تحديث الملف. أكّد بريدك الجديد.',
    'Password changed.': 'تم تغيير كلمة المرور.', 'Invalid email or password.': 'البريد أو كلمة المرور غير صحيحة.',
    'This account is disabled.': 'هذا الحساب معطّل.', 'Verify your email address before signing in.': 'أكّد بريدك الإلكتروني قبل تسجيل الدخول.',
    'Validation failed.': 'راجع البيانات المدخلة.', 'Too many requests. Please try again later.': 'محاولات كثيرة. حاول لاحقًا.',
    'Verification code': 'رمز التحقق',
    'Team account? Set up two-step verification': 'حساب فريق؟ فعّل التحقق بخطوتين',
    'Enter the verification code from your authenticator app, or a recovery code.': 'أدخل رمز التحقق من تطبيق المصادقة، أو أحد رموز الاسترداد.',
    'That verification code is not valid.': 'رمز التحقق غير صحيح.',
    'Too many failed sign-in attempts. Try again in 15 minutes.': 'محاولات دخول فاشلة كثيرة. حاول بعد ١٥ دقيقة.',
    'Team accounts sign in with email, password and a verification code.': 'حسابات الفريق تدخل بالبريد وكلمة المرور ورمز التحقق.',
    'Two-step verification is required for team accounts. Set it up at /account/mfa/enroll/ first.': 'التحقق بخطوتين مطلوب لحسابات الفريق. فعّله أولًا من /account/mfa/enroll/',
    'Switch language': 'English', 'Switch theme': 'تبديل المظهر', 'Back to the site': 'العودة للموقع', 'Account': 'الحساب',
    discovery: 'تحديد احتياج', consultation: 'استشارة', contact: 'تواصل',
    pending_review: 'بانتظار مراجعة الفريق', in_review: 'قيد المراجعة', needs_information: 'نحتاج معلومات إضافية',
    proposal_preparing: 'جارٍ إعداد العرض', proposal_sent: 'تم إرسال العرض', confirmed: 'مؤكد', completed: 'مكتمل',
    declined: 'تعذّر التنفيذ', canceled: 'ملغي', provisional: 'بانتظار التأكيد', submitted: 'تم الإرسال',
    status_changed: 'تغيّرت الحالة', note_updated: 'تحديث داخلي', pipeline_updated: 'تحديث داخلي', assigned: 'تم التعيين'
  };
  var EN_LABELS = {
    discovery: 'Discovery', consultation: 'Consultation', contact: 'Contact', pending_review: 'Awaiting team review',
    in_review: 'In review', needs_information: 'More information needed', proposal_preparing: 'Proposal in preparation',
    proposal_sent: 'Proposal shared', confirmed: 'Confirmed', completed: 'Completed', declined: 'Unable to proceed',
    canceled: 'Canceled', provisional: 'Pending confirmation', submitted: 'Submitted', status_changed: 'Status changed',
    note_updated: 'Internal update', pipeline_updated: 'Internal update', assigned: 'Assigned', 'Switch language': 'عربي'
  };
  function lang() { return localStorage.getItem('flowly-language') === 'ar' ? 'ar' : 'en'; }
  function t(s) { return lang() === 'ar' ? (AR[s] || s) : (EN_LABELS[s] || s); }
  function label(code) { return code ? t(code) : ''; }
  function applyPrefs() {
    var ar = lang() === 'ar';
    document.documentElement.lang = ar ? 'ar' : 'en';
    document.documentElement.dir = ar ? 'rtl' : 'ltr';
    document.documentElement.setAttribute('data-theme', localStorage.getItem('flowly-theme') === 'dark' ? 'dark' : 'light');
    document.title = (ar ? 'حسابي في Flowly' : 'My Flowly account');
  }

  function h(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'class') el.className = attrs[k];
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== false && attrs[k] != null) el.setAttribute(k, attrs[k]);
    });
    (function add(list) {
      list.forEach(function (c) {
        if (c == null || c === false) return;
        if (Array.isArray(c)) return add(c);
        el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      });
    })([].slice.call(arguments, 2));
    return el;
  }

  function api(path, opts, retry) {
    opts = opts || {};
    var headers = opts.headers || {};
    if (!(opts.body instanceof FormData) && opts.body) headers['Content-Type'] = 'application/json';
    if (store.access && !opts.anon) headers.Authorization = 'Bearer ' + store.access;
    return fetch(API + path, { method: opts.method || 'GET', headers: headers,
      body: opts.body instanceof FormData ? opts.body : (opts.body ? JSON.stringify(opts.body) : undefined) })
      .then(function (res) {
        if (res.status === 401 && !opts.anon && retry !== false && store.refresh) {
          return fetch(API + '/auth/token/refresh/', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh: store.refresh }) })
            .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
            .then(function (r) {
              if (!r.ok) { store.clear(); me = null; throw { status: 401, message: t('Session expired. Please sign in again.') }; }
              store.set(r.j.data.access, r.j.data.refresh);
              return api(path, opts, false);
            });
        }
        return res.json().catch(function () { return {}; }).then(function (j) {
          if (!res.ok) throw { status: res.status, message: t(j.message || 'Request failed.'), errors: j.errors };
          return j;
        });
      }, function () { throw { status: 0, message: t('Something went wrong.') }; });
  }

  function errorList(err) {
    var box = h('div', { role: 'alert' });
    box.appendChild(h('div', { class: 'msg err' }, err.message || t('Something went wrong.')));
    if (err.errors && typeof err.errors === 'object') {
      Object.keys(err.errors).forEach(function (k) {
        var v = err.errors[k];
        if (k === 'code' || k === 'retry_after') return;
        box.appendChild(h('p', { class: 'field-err' }, (k === 'non_field_errors' ? '' : k + ': ') + (Array.isArray(v) ? v.join(' ') : v)));
      });
    }
    return box;
  }

  function field(id, labelText, type, extra) {
    return [h('label', { for: id }, t(labelText)), h('input', Object.assign({ id: id, name: id, type: type || 'text' }, extra || {}))];
  }

  function form(children, onSubmit, submitLabel) {
    var status = h('div');
    var btn = h('button', { class: 'primary', type: 'submit' }, t(submitLabel));
    var f = h('form', { novalidate: 'novalidate' }, status);
    children.forEach(function (c) { [].concat(c).forEach(function (n) { f.appendChild(n); }); });
    f.appendChild(btn);
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      btn.disabled = true;
      status.replaceChildren();
      var data = {};
      new FormData(f).forEach(function (v, k) { data[k] = v; });
      Promise.resolve(onSubmit(data, f)).then(function (okMsg) {
        if (okMsg) status.appendChild(h('div', { class: 'msg ok', role: 'status' }, t(okMsg)));
      }).catch(function (err) { status.replaceChildren(errorList(err)); })
        .then(function () { btn.disabled = false; });
    });
    return f;
  }

  // replaceChildren() turns null into the text "null", so drop empty entries first.
  function render(nodes) {
    app.replaceChildren.apply(app, [].concat(nodes).filter(function (n) { return n != null && n !== false; }));
    app.focus({ preventScroll: true });
  }

  function renderTools() {
    tools.replaceChildren(
      h('a', { class: 'tool', href: '/' }, t('Back to the site')),
      h('button', { type: 'button', class: 'tool', 'aria-label': lang() === 'ar' ? 'Switch to English' : 'التبديل للعربية',
        onclick: function () { localStorage.setItem('flowly-language', lang() === 'ar' ? 'en' : 'ar'); applyPrefs(); route(); } }, t('Switch language')),
      h('button', { type: 'button', class: 'tool', 'aria-label': t('Switch theme'),
        onclick: function () { localStorage.setItem('flowly-theme', localStorage.getItem('flowly-theme') === 'dark' ? 'light' : 'dark'); applyPrefs(); } },
        localStorage.getItem('flowly-theme') === 'dark' ? '☀' : '☾'));
  }

  function renderNav(name) {
    nav.replaceChildren();
    var items = me ? [['dashboard', 'Dashboard'], ['requests', 'My requests'], ['profile', 'Profile']]
                   : [['login', 'Sign in'], ['register', 'Create account']];
    items.forEach(function (it) {
      nav.appendChild(h('a', { href: '#' + it[0], 'aria-current': name === it[0] ? 'page' : false }, t(it[1])));
    });
    if (me) nav.appendChild(h('button', { type: 'button', onclick: logout }, t('Sign out')));
    renderTools();
  }

  function logout() {
    var refresh = store.refresh;
    var done = function () { store.clear(); me = null; location.hash = '#login'; route(); };
    if (refresh) api('/auth/logout/', { method: 'POST', body: { refresh: refresh } }).then(done, done); else done();
  }

  function banner() {
    var q = new URLSearchParams(location.search), out = [];
    if (q.get('verified') === '1') out.push(h('div', { class: 'msg ok', role: 'status' }, t('Email verified. You can sign in now.')));
    if (q.get('verified') === '0') out.push(h('div', { class: 'msg err', role: 'alert' }, t('That verification link is invalid or expired. Request a new one by signing in.')));
    if (q.get('error') === 'google') out.push(h('div', { class: 'msg err', role: 'alert' }, t('Google sign-in did not complete. Please try again.')));
    return out;
  }

  function googleButton() {
    if (!GOOGLE) return null; // shown only when GOOGLE_CLIENT_ID/SECRET are configured on the server
    var box = h('div');
    box.appendChild(h('button', { class: 'google', type: 'button', onclick: function () {
      api('/auth/social/google/', { anon: true }).then(function (j) { location.href = j.data.authorization_url; })
        .catch(function (e) { box.replaceChildren(errorList(e)); });
    } }, t('Continue with Google')));
    return box;
  }

  function viewLogin() {
    // The code field stays hidden (and is not sent) until the server answers that this account needs a code.
    var codeInput = h('input', { id: 'code', name: 'code', type: 'text', dir: 'ltr', inputmode: 'numeric',
      autocomplete: 'one-time-code', disabled: 'disabled' });
    var codeBox = h('div', { hidden: 'hidden' }, h('label', { for: 'code' }, t('Verification code')), codeInput);
    function showCode() { codeBox.hidden = false; codeInput.disabled = false; codeInput.focus(); }
    var f = form([field('email', 'Email', 'email', { autocomplete: 'email', required: 'required' }),
      field('password', 'Password', 'password', { autocomplete: 'current-password', required: 'required' }),
      codeBox],
      function (d) {
        return api('/auth/login/', { method: 'POST', body: d, anon: true }).then(function (j) {
          store.set(j.data.access, j.data.refresh); me = j.data.user; location.hash = '#dashboard';
        }).catch(function (err) {
          var code = err.errors && err.errors.code;
          if (code === 'mfa_required' || code === 'mfa_invalid') showCode();
          if (code === 'email_not_verified') {
            api('/auth/resend-verification/', { method: 'POST', body: { email: d.email }, anon: true }).catch(function () {});
            err.message += ' ' + t('We sent a new verification link.');
          }
          throw err;
        });
      }, 'Sign in');
    render(h('section', { class: 'card narrow' }, h('h1', {}, t('Sign in')), banner(), f, googleButton(),
      h('p', { class: 'links' }, h('a', { class: 'link', href: '#forgot' }, t('Forgot your password?')), ' · ', h('a', { class: 'link', href: '#register' }, t('Create an account'))),
      h('p', { class: 'links' }, h('a', { class: 'link', href: '/account/mfa/enroll/' }, t('Team account? Set up two-step verification')))));
  }

  function viewRegister() {
    var f = form([field('first_name', 'First name', 'text', { autocomplete: 'given-name' }),
      field('last_name', 'Last name', 'text', { autocomplete: 'family-name' }),
      field('email', 'Email', 'email', { autocomplete: 'email', required: 'required' }),
      field('password', 'Password (8+ characters)', 'password', { autocomplete: 'new-password', required: 'required' }),
      field('password_confirm', 'Confirm password', 'password', { autocomplete: 'new-password', required: 'required' })],
      function (d) {
        return api('/auth/register/', { method: 'POST', body: d, anon: true }).then(function (j) { return j.message; });
      }, 'Create account');
    render(h('section', { class: 'card narrow' }, h('h1', {}, t('Create your account')), f, googleButton(),
      h('p', { class: 'links' }, h('a', { class: 'link', href: '#login' }, t('I already have an account')))));
  }

  function viewForgot() {
    var f = form([field('email', 'Email', 'email', { autocomplete: 'email', required: 'required' })],
      function (d) { return api('/auth/password/reset/', { method: 'POST', body: d, anon: true }).then(function (j) { return j.message; }); },
      'Send reset link');
    render(h('section', { class: 'card narrow' }, h('h1', {}, t('Reset your password')), f,
      h('p', { class: 'links' }, h('a', { class: 'link', href: '#login' }, t('Back to sign in')))));
  }

  function fmtDate(v) {
    if (!v) return '';
    return new Intl.DateTimeFormat(lang() === 'ar' ? 'ar-EG' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Cairo' }).format(new Date(v));
  }
  function pill(code) { return h('span', { class: 'pill' }, label(code)); }
  function table(headers, rows) {
    return h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, headers.map(function (x) { return h('th', {}, t(x)); }))), h('tbody', {}, rows)));
  }

  function viewDashboard() {
    render(h('p', {}, t('Loading…')));
    api('/dashboard/').then(function (j) {
      var d = j.data, nxt = d.next_appointment;
      var stats = h('div', { class: 'stats' },
        h('div', { class: 'stat' }, h('b', {}, String(d.total_requests)), t('Total requests')),
        h('div', { class: 'stat' }, h('b', {}, String(d.open_requests)), t('Open')),
        h('div', { class: 'stat' }, h('b', {}, nxt ? nxt.date : '—'),
          nxt ? t('Next consultation') + ' · ' + nxt.time + ' ' + t('Cairo') + ' (' + label(nxt.status) + ')' : t('No upcoming consultation')));
      var rows = d.recent.map(function (r) {
        return h('tr', {}, h('td', {}, h('a', { class: 'link', href: '#request/' + r.reference }, r.reference)), h('td', {}, label(r.kind)),
          h('td', {}, pill(r.status)), h('td', {}, fmtDate(r.created_at)));
      });
      render([h('h1', {}, t('Welcome') + (me && me.first_name ? (lang() === 'ar' ? '، ' : ', ') + me.first_name : '')),
        me && !me.email_verified ? h('div', { class: 'msg err' }, t('Your email is not verified yet.')) : null,
        h('section', { class: 'card' }, stats),
        h('section', { class: 'card' }, h('h2', {}, t('Recent requests')),
          rows.length ? table(['Reference', 'Type', 'Status', 'Submitted'], rows)
            : h('p', { class: 'muted' }, t('No requests yet. Submit one from the Flowly site and it will appear here.')),
          h('p', {}, h('a', { class: 'primary', href: '/consultation' }, t('Request a consultation')))),
        me && ['owner', 'staff', 'viewer'].indexOf(me.role) >= 0 ? h('section', { class: 'card' }, h('h2', {}, t('Team')),
          h('p', { class: 'muted' }, t('Manage requests in the admin site or the /team console.')),
          h('a', { class: 'link', href: '/team' }, t('Open /team console'))) : null]);
    }).catch(fail);
  }

  function viewRequests() {
    render(h('p', {}, t('Loading…')));
    api('/requests/mine/?ordering=-created_at&page_size=100').then(function (j) {
      var rows = j.data.results.map(function (r) {
        return h('tr', {}, h('td', {}, h('a', { class: 'link', href: '#request/' + r.reference }, r.reference)), h('td', {}, r.organization),
          h('td', {}, label(r.kind)), h('td', {}, pill(r.status)), h('td', {}, fmtDate(r.created_at)));
      });
      render([h('h1', {}, t('My requests')), h('section', { class: 'card' }, rows.length ?
        table(['Reference', 'Organization', 'Type', 'Status', 'Submitted'], rows) : h('p', { class: 'muted' }, t('No requests yet.')))]);
    }).catch(fail);
  }

  function viewRequest(ref) {
    render(h('p', {}, t('Loading…')));
    api('/requests/mine/' + encodeURIComponent(ref) + '/').then(function (j) {
      var r = j.data, a = r.appointment;
      var ap = a ? a.date + ' · ' + a.time + ' ' + t('Cairo') + ' · ' + label(a.status) : t('None');
      render([h('p', {}, h('a', { class: 'link', href: '#requests' }, t('← All requests'))),
        h('section', { class: 'card' }, h('h1', {}, r.reference),
          h('p', {}, pill(r.status), ' · ', label(r.kind), ' · ', r.organization),
          h('p', {}, t('Consultation') + ': ' + ap), h('h2', {}, t('Timeline')),
          h('ul', { class: 'timeline' }, r.events.map(function (e) {
            return h('li', {}, fmtDate(e.created_at) + ' — ' + label(e.event_type) + (e.status && e.event_type === 'status_changed' ? ' (' + label(e.status) + ')' : ''));
          })))]);
    }).catch(fail);
  }

  function viewProfile() {
    var avatar = me.avatar ? h('img', { class: 'avatar', src: me.avatar, alt: t('Your avatar') })
      : h('div', { class: 'avatar', 'aria-hidden': 'true' }, (me.first_name || me.email).charAt(0).toUpperCase());
    var profile = form([field('first_name', 'First name', 'text', { value: me.first_name || '' }),
      field('last_name', 'Last name', 'text', { value: me.last_name || '' }),
      field('email', 'Email', 'email', { value: me.email, required: 'required' })],
      function (d) { return api('/users/me/', { method: 'PATCH', body: d }).then(function (j) { me = j.data; renderNav('profile'); return j.message; }); },
      'Save profile');
    var avatarForm = form([h('label', { for: 'avatar' }, t('Avatar image (JPEG, PNG, WebP, GIF)')), h('input', { id: 'avatar', name: 'avatar', type: 'file', accept: 'image/jpeg,image/png,image/webp,image/gif' })],
      function (d, f) {
        var fd = new FormData(); var file = f.avatar.files[0];
        if (!file) return Promise.reject({ message: t('Choose an image first.') });
        fd.append('avatar', file);
        return api('/users/me/avatar/', { method: 'POST', body: fd }).then(function (j) { me = j.data; viewProfile(); });
      }, 'Upload avatar');
    var pwd = form([field('current_password', 'Current password', 'password', { autocomplete: 'current-password', required: 'required' }),
      field('new_password', 'New password', 'password', { autocomplete: 'new-password', required: 'required' })],
      function (d, f) { return api('/users/me/change-password/', { method: 'POST', body: d }).then(function (j) { f.reset(); return j.message; }); },
      'Change password');
    var del = form([field('password', 'Enter your password to confirm', 'password', { autocomplete: 'current-password' })],
      function (d) {
        if (!confirm(t('Delete your account? You will be signed out and cannot sign in again.'))) return Promise.resolve();
        return api('/users/me/', { method: 'DELETE', body: d }).then(function () { store.clear(); me = null; location.hash = '#login'; route(); });
      }, 'Delete account');
    del.querySelector('button.primary').className = 'danger';
    render([h('h1', {}, t('Profile')), h('section', { class: 'card' }, h('div', { class: 'row' }, avatar, h('div', {}, h('b', {}, me.email),
      h('div', { class: 'muted' }, t('Role') + ': ' + me.role + ' · ' + t(me.email_verified ? 'email verified' : 'email not verified')))), profile),
      h('section', { class: 'card' }, h('h2', {}, t('Avatar')), avatarForm),
      h('section', { class: 'card' }, h('h2', {}, t('Change password')), pwd),
      h('section', { class: 'card' }, h('h2', {}, t('Delete account')), h('p', { class: 'muted' }, t('Your account is disabled. Request history is kept for audit.')), del)]);
  }

  function fail(err) {
    if (err && err.status === 401) { location.hash = '#login'; me = null; return route(); }
    render(errorList(err || {}));
  }

  var PUBLIC = { login: viewLogin, register: viewRegister, forgot: viewForgot };

  function route() {
    var hash = (location.hash || '#login').slice(1);
    if (/^access=/.test(hash)) { // returned from Google: tokens arrive in the URL fragment, never in a URL sent to a server
      var p = new URLSearchParams(hash);
      store.set(p.get('access'), p.get('refresh'));
      history.replaceState(null, '', location.pathname);
      hash = 'dashboard';
    }
    var parts = hash.split('/'), name = parts[0];
    var needsAuth = ['dashboard', 'requests', 'request', 'profile'].indexOf(name) >= 0;
    var load = me || !store.access ? Promise.resolve() :
      api('/users/me/').then(function (j) { me = j.data; }).catch(function () { store.clear(); me = null; });
    load.then(function () {
      if (needsAuth && !me) { name = 'login'; if (location.hash !== '#login') { location.hash = '#login'; return; } }
      if (!needsAuth && me && (name === 'login' || name === 'register')) { location.hash = '#dashboard'; return; }
      currentRoute = name;
      renderNav(name);
      if (PUBLIC[name]) return PUBLIC[name]();
      if (name === 'dashboard') return viewDashboard();
      if (name === 'requests') return viewRequests();
      if (name === 'request') return viewRequest(decodeURIComponent(parts[1] || ''));
      if (name === 'profile') return viewProfile();
      return viewLogin();
    });
  }

  applyPrefs();
  window.addEventListener('hashchange', route);
  window.addEventListener('storage', function (e) { // keep in sync with the main site open in another tab
    if (e.key === 'flowly-language' || e.key === 'flowly-theme') { applyPrefs(); route(); }
  });
  route();
})();
