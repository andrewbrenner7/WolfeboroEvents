/* Optional events-email signup on guide, events, and join pages.
   Same checks as the home page form: honeypot, timing, Turnstile. */
(function () {
  var UTM_TTL_MS = 30 * 24 * 60 * 60 * 1000;
  function captureUtmParams() {
    try {
      var params = new URLSearchParams(window.location.search);
      var src = (params.get('utm_source') || '').trim().toLowerCase();
      if (/^[a-z0-9_-]{1,25}$/.test(src)) {
        try { sessionStorage.setItem('sc_utm_source', src); } catch (e1) {}
        try { localStorage.setItem('sc_utm_source_30d', JSON.stringify({ value: src, ts: Date.now() })); } catch (e2) {}
      }
      ['utm_medium', 'utm_campaign', 'utm_content'].forEach(function (k) {
        var v = (params.get(k) || '').trim().toLowerCase();
        if (/^[a-z0-9_-]{1,40}$/.test(v)) {
          try { sessionStorage.setItem('sc_' + k, v); } catch (e3) {}
        }
      });
    } catch (e) {}
  }
  function getStoredUtmSource() {
    try {
      var params = new URLSearchParams(window.location.search);
      var fromUrl = (params.get('utm_source') || '').trim().toLowerCase();
      if (/^[a-z0-9_-]{1,25}$/.test(fromUrl)) return fromUrl;
    } catch (e1) {}
    try {
      var fromSess = (sessionStorage.getItem('sc_utm_source') || '').trim().toLowerCase();
      if (/^[a-z0-9_-]{1,25}$/.test(fromSess)) return fromSess;
    } catch (e2) {}
    try {
      var raw = localStorage.getItem('sc_utm_source_30d');
      if (raw) {
        var parsed = JSON.parse(raw);
        if (parsed && parsed.value && parsed.ts && (Date.now() - Number(parsed.ts) <= UTM_TTL_MS)) {
          var fromLocal = String(parsed.value).trim().toLowerCase();
          if (/^[a-z0-9_-]{1,25}$/.test(fromLocal)) return fromLocal;
        }
      }
    } catch (e3) {}
    return '';
  }
  captureUtmParams();

  var form = document.getElementById('signup-form');
  if (!form) return;
  var statusEl = document.getElementById('signup-status');
  var submitBtn = document.getElementById('signup-submit');
  if (form.ts) form.ts.value = String(Date.now());
  function showError(text) {
    statusEl.hidden = false;
    statusEl.className = 'signup-status error';
    statusEl.textContent = text;
  }
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var email = (form.email.value || '').trim();
    var website = (form.website && form.website.value) || '';
    if (submitBtn.disabled) return;
    if (!email) {
      showError('Please enter your email.');
      return;
    }
    var tsToken = (form.querySelector('[name="cf-turnstile-response"]') || {}).value || '';
    if (window.turnstile && form.querySelector('.cf-turnstile') && !tsToken) {
      showError('Please check the box and try again.');
      return;
    }
    var btnLabel = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Joining...';
    statusEl.hidden = true;
    var page = (form.page && form.page.value) || window.location.pathname;
    var sourcePage = ((form.source_page && form.source_page.value) || '').trim().toLowerCase();
    var listName = (form.list && form.list.value) || 'oaks';
    var storedUtm = getStoredUtmSource();
    storedUtm = /^[a-z0-9_-]{1,25}$/.test(storedUtm) ? storedUtm : '';
    var effectiveSourcePage = storedUtm ? (storedUtm + '_' + (sourcePage || 'page')).slice(0, 40) : (sourcePage || page);
    var effectiveSource = (storedUtm === 'sign' || storedUtm === 'qr' || storedUtm === 'flyer') ? 'flyer_qr' : (storedUtm || 'website');
    if (typeof gtag === 'function') {
      gtag('event', 'generate_lead', { property: listName, method: 'native_form', lead_source: storedUtm || 'website', page: page, source_page: effectiveSourcePage });
    }
    fetch('/.netlify/functions/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email,
        list: listName,
        source: effectiveSource,
        source_page: effectiveSourcePage,
        page: page,
        website: website,
        ts: form.ts ? form.ts.value : '',
        elapsed: form.ts && form.ts.value ? Date.now() - Number(form.ts.value) : 0,
        turnstile: tsToken
      })
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          return { ok: res.ok && data && data.ok, status: res.status, data: data || {} };
        });
      })
      .then(function (result) {
        if (result.ok) {
          var done = document.createElement('p');
          done.className = 'signup-status';
          done.setAttribute('role', 'status');
          done.setAttribute('aria-live', 'polite');
          done.innerHTML = '<strong>Thanks, you\u2019re on the list.</strong> Your first note is headed your way.';
          form.parentNode.replaceChild(done, form);
          return;
        }
        var text = 'Something went wrong on our end. Give it a minute and try again.';
        if (result.status === 403) text = 'Please check the box and try again.';
        else if (result.status === 400 && result.data.error === 'Invalid email') text = 'Hmm, that email address doesn\u2019t look right. Mind checking it?';
        else if (result.status === 429) text = 'Too many tries. Please wait a few minutes and try again.';
        throw new Error(text);
      })
      .catch(function (err) {
        var text = err && err.message && (err.message.indexOf('try again') !== -1 || err.message.indexOf('Mind checking') !== -1) ? err.message : 'Something went wrong on our end. Give it a minute and try again.';
        showError(text);
        submitBtn.disabled = false;
        submitBtn.textContent = btnLabel;
        if (window.turnstile) { try { window.turnstile.reset(); } catch (e2) {} }
      });
  });
})();
