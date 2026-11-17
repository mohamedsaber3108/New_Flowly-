/* Flowly account portal: login, register, password reset, dashboard, requests, profile.
   Plain JS, no build step. All text is inserted with textContent (no HTML injection). */
(function () {
  'use strict';
  var API = '/api/v1';
  var app = document.getElementById('app');
  var nav = document.getElementById('nav');
  var store = {
    get access() { return localStorage.getItem('flowly-access'); },
    get refresh() { return localStorage.getItem('flowly-refresh'); },
    set: function (a, r) { localStorage.setItem('flowly-access', a); if (r) localStorage.setItem('flowly-refresh', r); },
    clear: function () { localStorage.removeItem('flowly-access'); localStorage.removeItem('flowly-refresh'); }
  };
  var me = null;

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
              if (!r.ok) { store.clear(); me = null; throw { status: 401, message: 'Session expired. Please sign in again.' }; }
              store.set(r.j.data.access, r.j.data.refresh);
              return api(path, opts, false);
            });
        }
        return res.json().catch(function () { return {}; }).then(function (j) {
          if (!res.ok) throw { status: res.status, message: j.message || 'Request failed.', errors: j.errors };
          return j;
        });
      });
  }

  function errorList(err) {
    var box = h('div', { role: 'alert' });
    box.appendChild(h('div', { class: 'msg err' }, err.message || 'Something went wrong.'));
    if (err.errors && typeof err.errors === 'object') {
      Object.keys(err.errors).forEach(function (k) {
        var v = err.errors[k];
        if (k === 'code' || k === 'retry_after') return;
        box.appendChild(h('p', { class: 'field-err' }, k + ': ' + (Array.isArray(v) ? v.join(' ') : v)));
      });
    }
    return box;
  }

  function field(id, label, type, extra) {
    return [h('label', { for: id }, label), h('input', Object.assign({ id: id, name: id, type: type || 'text' }, extra || {}))];
  }

  function form(children, onSubmit, submitLabel) {
    var status = h('div');
    var btn = h('button', { class: 'primary', type: 'submit' }, submitLabel);
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
        if (okMsg) status.appendChild(h('div', { class: 'msg ok', role: 'status' }, okMsg));
      }).catch(function (err) { status.replaceChildren(errorList(err)); })
        .then(function () { btn.disabled = false; });
    });
    return f;
  }

  function render(nodes) { app.replaceChildren.apply(app, [].concat(nodes)); app.focus({ preventScroll: true }); }

  function renderNav(route) {
    nav.replaceChildren();
    var items = me ? [['dashboard', 'Dashboard'], ['requests', 'My requests'], ['profile', 'Profile']]
                   : [['login', 'Sign in'], ['register', 'Create account']];
    items.forEach(function (it) {
      nav.appendChild(h('a', { href: '#' + it[0], 'aria-current': route === it[0] ? 'page' : false }, it[1]));
    });
    if (me) nav.appendChild(h('button', { type: 'button', onclick: logout }, 'Sign out'));
  }

  function logout() {
    var refresh = store.refresh;
    var done = function () { store.clear(); me = null; location.hash = '#login'; route(); };
    if (refresh) api('/auth/logout/', { method: 'POST', body: { refresh: refresh } }).then(done, done); else done();
  }

  function banner() {
    var q = new URLSearchParams(location.search), out = [];
    if (q.get('verified') === '1') out.push(h('div', { class: 'msg ok', role: 'status' }, 'Email verified. You can sign in now.'));
    if (q.get('verified') === '0') out.push(h('div', { class: 'msg err', role: 'alert' }, 'That verification link is invalid or expired. Request a new one by signing in.'));
    if (q.get('error') === 'google') out.push(h('div', { class: 'msg err', role: 'alert' }, 'Google sign-in did not complete. Please try again.'));
    return out;
  }

  function googleButton() {
    return h('button', { class: 'google', type: 'button', onclick: function () {
      api('/auth/social/google/', { anon: true }).then(function (j) { location.href = j.data.authorization_url; })
        .catch(function (e) { alert(e.message); });
    } }, 'Continue with Google');
  }

  function viewLogin() {
    var f = form([field('email', 'Email', 'email', { autocomplete: 'email', required: 'required' }),
      field('password', 'Password', 'password', { autocomplete: 'current-password', required: 'required' })],
      function (d) {
        return api('/auth/login/', { method: 'POST', body: d, anon: true }).then(function (j) {
          store.set(j.data.access, j.data.refresh); me = j.data.user; location.hash = '#dashboard'; route();
        }).catch(function (err) {
          if (err.errors && err.errors.code === 'email_not_verified') {
            err.message += ' ';
            api('/auth/resend-verification/', { method: 'POST', body: { email: d.email }, anon: true }).catch(function () {});
            err.message += 'We sent a new verification link.';
          }
          throw err;
        });
      }, 'Sign in');
    render(h('section', { class: 'card narrow' }, h('h1', {}, 'Sign in'), banner(), f, googleButton(),
      h('p', {}, h('a', { class: 'link', href: '#forgot' }, 'Forgot your password?'), ' · ', h('a', { class: 'link', href: '#register' }, 'Create an account'))));
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
    render(h('section', { class: 'card narrow' }, h('h1', {}, 'Create your account'), f, googleButton(),
      h('p', {}, h('a', { class: 'link', href: '#login' }, 'I already have an account'))));
  }

  function viewForgot() {
    var f = form([field('email', 'Email', 'email', { autocomplete: 'email', required: 'required' })],
      function (d) { return api('/auth/password/reset/', { method: 'POST', body: d, anon: true }).then(function (j) { return j.message; }); },
      'Send reset link');
    render(h('section', { class: 'card narrow' }, h('h1', {}, 'Reset your password'), f,
      h('p', {}, h('a', { class: 'link', href: '#login' }, 'Back to sign in'))));
  }

  function fmtDate(v) { return v ? new Date(v).toLocaleString() : ''; }

  function viewDashboard() {
    render(h('p', {}, 'Loading…'));
    api('/dashboard/').then(function (j) {
      var d = j.data;
      var stats = h('div', { class: 'stats' },
        h('div', { class: 'stat' }, h('b', {}, String(d.total_requests)), 'Total requests'),
        h('div', { class: 'stat' }, h('b', {}, String(d.open_requests)), 'Open'),
        h('div', { class: 'stat' }, h('b', {}, d.next_appointment ? d.next_appointment.date : '—'),
          d.next_appointment ? 'Next consultation · ' + d.next_appointment.time + ' Cairo (' + d.next_appointment.status + ')' : 'No upcoming consultation'));
      var rows = d.recent.map(function (r) {
        return h('tr', {}, h('td', {}, h('a', { class: 'link', href: '#request/' + r.reference }, r.reference)), h('td', {}, r.kind),
          h('td', {}, h('span', { class: 'pill' }, r.status.replace(/_/g, ' '))), h('td', {}, fmtDate(r.created_at)));
      });
      var table = rows.length ? h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Reference'), h('th', {}, 'Type'), h('th', {}, 'Status'), h('th', {}, 'Submitted'))), h('tbody', {}, rows))
        : h('p', { class: 'muted' }, 'No requests yet. Submit one from the Flowly site and it will appear here.');
      render([h('h1', {}, 'Welcome' + (me && me.first_name ? ', ' + me.first_name : '')),
        me && !me.email_verified ? h('div', { class: 'msg err' }, 'Your email is not verified yet.') : null,
        h('section', { class: 'card' }, stats),
        h('section', { class: 'card' }, h('h2', {}, 'Recent requests'), table,
          h('p', {}, h('a', { class: 'primary', href: '/consultation' }, 'Request a consultation'))),
        me && ['owner', 'staff', 'viewer'].indexOf(me.role) >= 0 ? h('section', { class: 'card' }, h('h2', {}, 'Team'),
          h('p', { class: 'muted' }, 'Manage requests in the admin site or the /team console.'),
          h('a', { class: 'link', href: '/team' }, 'Open /team console')) : null]);
    }).catch(fail);
  }

  function viewRequests() {
    render(h('p', {}, 'Loading…'));
    api('/requests/mine/?ordering=-created_at').then(function (j) {
      var rows = j.data.results.map(function (r) {
        return h('tr', {}, h('td', {}, h('a', { class: 'link', href: '#request/' + r.reference }, r.reference)), h('td', {}, r.organization),
          h('td', {}, r.kind), h('td', {}, h('span', { class: 'pill' }, r.status.replace(/_/g, ' '))), h('td', {}, fmtDate(r.created_at)));
      });
      render([h('h1', {}, 'My requests'), h('section', { class: 'card' }, rows.length ?
        h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Reference'), h('th', {}, 'Organization'), h('th', {}, 'Type'), h('th', {}, 'Status'), h('th', {}, 'Submitted'))), h('tbody', {}, rows))
        : h('p', { class: 'muted' }, 'No requests yet.'))]);
    }).catch(fail);
  }

  function viewRequest(ref) {
    render(h('p', {}, 'Loading…'));
    api('/requests/mine/' + encodeURIComponent(ref) + '/').then(function (j) {
      var r = j.data;
      var ap = r.appointment ? r.appointment.date + ' ' + r.appointment.time + ' (' + r.appointment.timezone + ', ' + r.appointment.status + ')' : 'None';
      render([h('p', {}, h('a', { class: 'link', href: '#requests' }, '← All requests')),
        h('section', { class: 'card' }, h('h1', {}, r.reference),
          h('p', {}, h('span', { class: 'pill' }, r.status.replace(/_/g, ' ')), ' · ', r.kind, ' · ', r.organization),
          h('p', {}, 'Consultation: ' + ap), h('h2', {}, 'Timeline'),
          h('ul', { class: 'timeline' }, r.events.map(function (e) {
            return h('li', {}, fmtDate(e.created_at) + ' — ' + e.event_type.replace(/_/g, ' ') + (e.status ? ' (' + e.status.replace(/_/g, ' ') + ')' : ''));
          })))]);
    }).catch(fail);
  }

  function viewProfile() {
    var avatar = me.avatar ? h('img', { class: 'avatar', src: me.avatar, alt: 'Your avatar' })
      : h('div', { class: 'avatar', 'aria-hidden': 'true' }, (me.first_name || me.email).charAt(0).toUpperCase());
    var profile = form([field('first_name', 'First name', 'text', { value: me.first_name || '' }),
      field('last_name', 'Last name', 'text', { value: me.last_name || '' }),
      field('email', 'Email', 'email', { value: me.email, required: 'required' })],
      function (d) { return api('/users/me/', { method: 'PATCH', body: d }).then(function (j) { me = j.data; renderNav('profile'); return j.message; }); },
      'Save profile');
    var avatarForm = form([h('label', { for: 'avatar' }, 'Avatar image (JPEG, PNG, WebP, GIF)'), h('input', { id: 'avatar', name: 'avatar', type: 'file', accept: 'image/*' })],
      function (d, f) {
        var fd = new FormData(); var file = f.avatar.files[0];
        if (!file) return Promise.reject({ message: 'Choose an image first.' });
        fd.append('avatar', file);
        return api('/users/me/avatar/', { method: 'POST', body: fd }).then(function (j) { me = j.data; viewProfile(); });
      }, 'Upload avatar');
    var pwd = form([field('current_password', 'Current password', 'password', { autocomplete: 'current-password', required: 'required' }),
      field('new_password', 'New password', 'password', { autocomplete: 'new-password', required: 'required' })],
      function (d, f) { return api('/users/me/change-password/', { method: 'POST', body: d }).then(function (j) { f.reset(); return j.message; }); },
      'Change password');
    var del = form([field('password', 'Enter your password to confirm', 'password', { autocomplete: 'current-password' })],
      function (d) {
        if (!confirm('Delete your account? You will be signed out and cannot sign in again.')) return Promise.resolve();
        return api('/users/me/', { method: 'DELETE', body: d }).then(function () { store.clear(); me = null; location.hash = '#login'; route(); });
      }, 'Delete account');
    del.querySelector('button.primary').className = 'danger';
    render([h('h1', {}, 'Profile'), h('section', { class: 'card' }, h('div', { class: 'row' }, avatar, h('div', {}, h('b', {}, me.email), h('div', { class: 'muted' }, 'Role: ' + me.role + (me.email_verified ? ' · email verified' : ' · email not verified')))), profile),
      h('section', { class: 'card' }, h('h2', {}, 'Avatar'), avatarForm),
      h('section', { class: 'card' }, h('h2', {}, 'Change password'), pwd),
      h('section', { class: 'card' }, h('h2', {}, 'Delete account'), h('p', { class: 'muted' }, 'Your account is disabled. Request history is kept for audit.'), del)]);
  }

  function fail(err) {
    if (err && err.status === 401) { location.hash = '#login'; me = null; return route(); }
    render(errorList(err || {}));
  }

  var PUBLIC = { login: viewLogin, register: viewRegister, forgot: viewForgot };

  function route() {
    var hash = (location.hash || '#login').slice(1);
    if (/^access=/.test(hash)) { // returned from Google: tokens arrive in the URL fragment
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
      if (needsAuth && !me) { name = 'login'; location.hash = '#login'; }
      if (!needsAuth && me && (name === 'login' || name === 'register')) { name = 'dashboard'; location.hash = '#dashboard'; }
      renderNav(name);
      if (PUBLIC[name]) return PUBLIC[name]();
      if (name === 'dashboard') return viewDashboard();
      if (name === 'requests') return viewRequests();
      if (name === 'request') return viewRequest(decodeURIComponent(parts[1] || ''));
      if (name === 'profile') return viewProfile();
      return viewLogin();
    });
  }

  window.addEventListener('hashchange', route);
  route();
})();
