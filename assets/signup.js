/* Optional events-email signup on guide and events pages (list=oaks).
   Same checks as the home page form: honeypot, timing, Turnstile. */
(function () {
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
    var sourcePage = (form.source_page && form.source_page.value) || '';
    if (typeof gtag === 'function') {
      gtag('event', 'generate_lead', { property: 'oaks', method: 'native_form', lead_source: 'website', page: page, source_page: sourcePage || page });
    }
    fetch('/.netlify/functions/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email,
        list: 'oaks',
        source: 'website',
        source_page: sourcePage,
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
