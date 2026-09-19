(() => {
  'use strict';

  const nativeShell = location.hostname === 'localhost' && location.protocol === 'https:';
  const API_BASE = nativeShell ? 'https://nottle-ai.onrender.com' : '';
  const TOKEN_KEY = 'nottle_ai_session';
  const state = { token: localStorage.getItem(TOKEN_KEY), user: null, business: null, calls: [], selectedCall: null, config: null };
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  }

  function apiErrorMessage(data, fallback) {
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail) && data.detail[0]?.msg) return data.detail[0].msg.replace(/^Value error, /, '');
    return fallback || 'Something went wrong. Please try again.';
  }

  async function api(path, options = {}) {
    const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    } catch (_) {
      throw new Error('Cannot reach NOTTLE AI. Check your internet connection and try again.');
    }
    let data = null;
    if (response.status !== 204) {
      const text = await response.text();
      try { data = text ? JSON.parse(text) : null; } catch (_) { data = null; }
    }
    if (!response.ok) {
      if (response.status === 401 && state.token && path !== '/api/auth/login') signOut(false);
      throw new Error(apiErrorMessage(data, `Request failed (${response.status})`));
    }
    return data;
  }

  let toastTimer;
  function toast(message, error = false) {
    const element = $('#toast');
    element.textContent = message;
    element.classList.toggle('error', error);
    element.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => element.classList.remove('show'), 3600);
  }

  async function busy(button, work) {
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span>Working…</span>';
    try { return await work(); }
    finally { button.disabled = false; button.innerHTML = original; }
  }

  function showAuth(card = 'login') {
    $('#loadingView').classList.add('hidden');
    $('#appView').classList.add('hidden');
    $('#authView').classList.remove('hidden');
    ['login', 'register', 'reset'].forEach(name => $(`#${name}Card`).classList.toggle('hidden', name !== card));
  }

  function showApp() {
    $('#loadingView').classList.add('hidden');
    $('#authView').classList.add('hidden');
    $('#appView').classList.remove('hidden');
    hydrateProfile();
    showPage('dashboard');
  }

  function initials(name) {
    return String(name || 'NA').split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0].toUpperCase()).join('');
  }

  function hydrateProfile() {
    const user = state.user || {};
    const business = state.business || {};
    $('#profileName').textContent = user.full_name || 'Account';
    $('#profileBusiness').textContent = business.name || 'Business';
    $('#profileInitials').textContent = initials(user.full_name);
    $('#mobileProfile').textContent = initials(user.full_name);
    $('#settingsEmail').textContent = user.email || '—';
    $('#settingsPlan').textContent = `${titleCase(business.plan || 'starter')} · ${titleCase(business.subscription_status || 'trial')}`;
    $('#adminNav').classList.toggle('hidden', !user.is_admin);
    const hour = new Date().getHours();
    const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
    $('#welcomeHeading').textContent = `${greeting}, ${(user.full_name || '').split(' ')[0] || 'there'}`;
    fillAssistantForm();
  }

  function titleCase(value) {
    return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
  }

  function showPage(page) {
    $$('.page').forEach(element => element.classList.toggle('active', element.id === `page-${page}`));
    $$('.nav-item[data-page]').forEach(element => element.classList.toggle('active', element.dataset.page === page));
    if (page === 'admin' && state.user?.is_admin) loadAdmin();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function setSession(payload) {
    state.token = payload.token;
    state.user = payload.user;
    state.business = payload.business;
    localStorage.setItem(TOKEN_KEY, state.token);
  }

  function signOut(showMessage = true) {
    state.token = null;
    state.user = null;
    state.business = null;
    state.calls = [];
    localStorage.removeItem(TOKEN_KEY);
    showAuth('login');
    if (showMessage) toast('Signed out successfully.');
  }

  async function logout() {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) { /* local logout still works */ }
    signOut();
  }

  async function loadAll() {
    const [dashboard, calls] = await Promise.all([api('/api/dashboard'), api('/api/calls?limit=100')]);
    state.business = dashboard.business;
    state.calls = calls.calls || [];
    hydrateProfile();
    renderDashboard(dashboard);
    renderCalls();
  }

  function renderDashboard(data) {
    const stats = data.stats || {};
    const business = state.business || {};
    $('#metricCalls').textContent = stats.calls || 0;
    $('#metricLeads').textContent = stats.leads || 0;
    $('#metricBookings').textContent = stats.bookings || 0;
    $('#metricMinutes').textContent = `${Math.max(0, Math.round((stats.seconds || 0) / 60))}m`;
    $('#callBadge').textContent = stats.calls || 0;
    $('#callBadge').classList.toggle('hidden', !(stats.calls > 0));
    $('#businessArea').textContent = business.area || 'Available 24/7';
    const active = business.phone_status === 'active' && !data.trial_expired;
    const paused = business.phone_status === 'paused' || data.trial_expired;
    const assistant = business.assistant_name || 'Nottle';
    $('#assistantName').textContent = active ? `${assistant} is answering your calls` : `${assistant} is ready to learn your business`;
    $('#assistantStatus').textContent = active ? 'Live and answering' : paused ? 'Service paused' : 'Setup pending';
    $('#assistantMessage').textContent = active
      ? 'Your AI receptionist is online and ready to capture the next customer enquiry.'
      : paused ? 'Contact support to restore your assistant.' : 'Complete the short setup and we’ll prepare your AI phone number.';
    $('#assistantDot').className = `live-dot ${active ? '' : paused ? 'paused' : 'pending'}`.trim();
    $('#businessNumber').textContent = active ? (business.phone_display || 'Active') : 'Pending setup';
    const callButton = $('#callAssistantButton');
    callButton.classList.toggle('disabled', !active || !business.phone_display);
    callButton.href = active ? `tel:${String(business.phone_display).replace(/[^+\d]/g, '')}` : '#';
    $('#trialBanner').classList.toggle('hidden', active || business.onboarding_completed);
    renderCallList($('#recentCalls'), state.calls.slice(0, 5), true);
  }

  function formatDate(value) {
    if (!value) return 'Unknown time';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }

  function formatDuration(seconds) {
    const total = Number(seconds) || 0;
    if (total < 60) return `${total}s`;
    return `${Math.floor(total / 60)}m ${total % 60}s`;
  }

  function callRow(call) {
    const tags = [
      call.booking_requested ? '<span class="tag booking">Booking</span>' : '',
      call.is_lead ? '<span class="tag lead">Lead</span>' : '',
      call.status === 'error' ? '<span class="tag error">Error</span>' : ''
    ].join('');
    return `<article class="call-row" data-call-id="${Number(call.id)}">
      <div class="caller-avatar">${escapeHtml(initials(call.caller === 'Unknown caller' ? 'Caller' : call.caller))}</div>
      <div class="call-person"><b>${escapeHtml(call.caller || 'Unknown caller')}</b><small>${escapeHtml(formatDate(call.created_at))}</small></div>
      <div class="call-summary"><b>${escapeHtml(call.summary || 'Call captured. Open for details.')}</b><small>${escapeHtml(formatDuration(call.duration_seconds))}</small></div>
      <div class="call-tags">${tags}</div>
    </article>`;
  }

  function renderCallList(container, calls, compact = false) {
    if (!calls.length) {
      container.innerHTML = `<div class="empty-state"><span>↗</span><b>No calls yet</b><p>${compact ? 'Your first AI-handled call will appear here.' : 'Calls will appear here once your number is active.'}</p></div>`;
      return;
    }
    container.innerHTML = calls.map(callRow).join('');
  }

  function filteredCalls() {
    const query = ($('#callSearch').value || '').trim().toLowerCase();
    const filter = $('#callFilter').value;
    return state.calls.filter(call => {
      const searchable = `${call.caller || ''} ${call.summary || ''} ${call.transcript || ''}`.toLowerCase();
      const matchesQuery = !query || searchable.includes(query);
      const matchesFilter = filter === 'all' || (filter === 'lead' && call.is_lead) || (filter === 'booking' && call.booking_requested);
      return matchesQuery && matchesFilter;
    });
  }

  function renderCalls() {
    renderCallList($('#allCalls'), filteredCalls());
  }

  function openCall(callId) {
    const call = state.calls.find(item => Number(item.id) === Number(callId));
    if (!call) return;
    state.selectedCall = call;
    $('#callDialogTitle').textContent = call.caller || 'Unknown caller';
    $('#callDialogMeta').innerHTML = [formatDate(call.created_at), formatDuration(call.duration_seconds), call.booking_requested ? 'Booking requested' : 'Enquiry'].map(value => `<span>${escapeHtml(value)}</span>`).join('');
    $('#callDialogSummary').textContent = call.summary || 'No summary was captured.';
    const turns = String(call.transcript || '').split('\n').filter(Boolean);
    $('#callDialogTranscript').innerHTML = turns.length ? turns.map(turn => {
      const match = turn.match(/^(Caller|AI):\s*(.*)$/s);
      const speaker = match?.[1] || 'Call';
      const text = match?.[2] || turn;
      return `<div class="turn ${speaker === 'AI' ? 'ai' : 'caller'}"><span>${escapeHtml(speaker)}</span>${escapeHtml(text)}</div>`;
    }).join('') : '<div class="empty-state"><b>No transcript available</b></div>';
    $('#callDialog').showModal();
  }

  function fillAssistantForm() {
    const form = $('#assistantForm');
    if (!form || !state.business) return;
    [...form.elements].forEach(element => {
      if (element.name && Object.prototype.hasOwnProperty.call(state.business, element.name)) {
        element.value = state.business[element.name] ?? '';
      }
    });
  }

  function formObject(form) {
    const data = Object.fromEntries(new FormData(form).entries());
    $$('input[type="checkbox"]', form).forEach(input => { data[input.name] = input.checked; });
    return data;
  }

  async function saveAssistant(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const button = $('button[type="submit"]', form);
    await busy(button, async () => {
      const payload = { ...formObject(form), onboarding_completed: true };
      try {
        const result = await api('/api/business', { method: 'PATCH', body: JSON.stringify(payload) });
        state.business = result.business;
        hydrateProfile();
        await loadAll();
        $('#saveStatus').textContent = 'All changes saved';
        toast('Assistant settings saved.');
        showPage('dashboard');
      } catch (error) { toast(error.message, true); }
    });
  }

  async function submitLogin(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const button = $('button[type="submit"]', form);
    await busy(button, async () => {
      try {
        const payload = await api('/api/auth/login', { method: 'POST', body: JSON.stringify(formObject(form)) });
        setSession(payload);
        showApp();
        await loadAll();
      } catch (error) { toast(error.message, true); }
    });
  }

  async function submitRegister(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const button = $('button[type="submit"]', form);
    await busy(button, async () => {
      try {
        const payload = await api('/api/auth/register', { method: 'POST', body: JSON.stringify(formObject(form)) });
        setSession(payload);
        showApp();
        await loadAll();
        showPage('assistant');
        toast('Account created. Let’s set up your receptionist.');
      } catch (error) { toast(error.message, true); }
    });
  }

  async function requestReset(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const button = $('button[type="submit"]', form);
    await busy(button, async () => {
      try {
        const result = await api('/api/auth/request-reset', { method: 'POST', body: JSON.stringify(formObject(form)) });
        toast(result.message);
        showAuth('login');
      } catch (error) { toast(error.message, true); }
    });
  }

  async function finishReset(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const token = new URLSearchParams(location.search).get('reset');
    const button = $('button[type="submit"]', form);
    await busy(button, async () => {
      try {
        const result = await api('/api/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, password: form.password.value }) });
        history.replaceState({}, '', '/');
        toast(result.message);
        showAuth('login');
      } catch (error) { toast(error.message, true); }
    });
  }

  async function exportData() {
    try {
      const data = await api('/api/account/export');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `nottle-ai-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast('Your data export is ready.');
    } catch (error) { toast(error.message, true); }
  }

  async function deleteAccount(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const button = $('button[type="submit"]', form);
    await busy(button, async () => {
      try {
        await api('/api/account', { method: 'DELETE', body: JSON.stringify(formObject(form)) });
        $('#deleteDialog').close();
        signOut(false);
        toast('Your NOTTLE AI account and stored data were deleted.');
      } catch (error) { toast(error.message, true); }
    });
  }

  async function deleteSelectedCall() {
    if (!state.selectedCall || !confirm('Delete this call and its transcript permanently?')) return;
    try {
      await api(`/api/calls/${state.selectedCall.id}`, { method: 'DELETE' });
      state.calls = state.calls.filter(call => call.id !== state.selectedCall.id);
      $('#callDialog').close();
      renderCalls();
      await loadAll();
      toast('Call deleted.');
    } catch (error) { toast(error.message, true); }
  }

  async function loadAdmin() {
    const container = $('#adminBusinesses');
    container.innerHTML = '<div class="empty-state"><b>Loading accounts…</b></div>';
    try {
      const data = await api('/api/admin/businesses');
      if (!data.businesses.length) {
        container.innerHTML = '<div class="empty-state"><b>No customer accounts</b></div>';
        return;
      }
      container.innerHTML = data.businesses.map(business => `<article class="admin-row" data-business-id="${business.id}">
        <div><b>${escapeHtml(business.name)}</b><small>${escapeHtml(business.owner_email || 'System account')} · ${business.call_count || 0} calls</small></div>
        <input data-admin-phone value="${escapeHtml(business.phone_display || '')}" placeholder="Phone number">
        <select data-admin-status><option value="pending" ${business.phone_status === 'pending' ? 'selected' : ''}>Number pending</option><option value="active" ${business.phone_status === 'active' ? 'selected' : ''}>Number active</option><option value="paused" ${business.phone_status === 'paused' ? 'selected' : ''}>Number paused</option></select>
        <button class="button quiet small" data-admin-save type="button">Save</button>
      </article>`).join('');
    } catch (error) { container.innerHTML = `<div class="empty-state"><b>${escapeHtml(error.message)}</b></div>`; }
  }

  async function saveAdminRow(row, button) {
    await busy(button, async () => {
      try {
        await api(`/api/admin/businesses/${row.dataset.businessId}`, { method: 'PATCH', body: JSON.stringify({ phone_display: $('[data-admin-phone]', row).value, phone_status: $('[data-admin-status]', row).value }) });
        toast('Customer account updated.');
      } catch (error) { toast(error.message, true); }
    });
  }

  function bindEvents() {
    $('#loginForm').addEventListener('submit', submitLogin);
    $('#registerForm').addEventListener('submit', submitRegister);
    $('#requestResetForm').addEventListener('submit', requestReset);
    $('#finishResetForm').addEventListener('submit', finishReset);
    $('#assistantForm').addEventListener('submit', saveAssistant);
    $('#deleteAccountForm').addEventListener('submit', deleteAccount);
    $('#showRegister').addEventListener('click', () => showAuth('register'));
    $('#showLogin').addEventListener('click', () => showAuth('login'));
    $('#forgotButton').addEventListener('click', () => showAuth('reset'));
    $('#resetBack').addEventListener('click', () => showAuth('login'));
    $('#logoutButton').addEventListener('click', logout);
    $('#settingsLogout').addEventListener('click', logout);
    $('#mobileProfile').addEventListener('click', () => showPage('settings'));
    $('#exportData').addEventListener('click', exportData);
    $('#deleteAccountButton').addEventListener('click', () => $('#deleteDialog').showModal());
    $('#deleteCall').addEventListener('click', deleteSelectedCall);
    $('#callSearch').addEventListener('input', renderCalls);
    $('#callFilter').addEventListener('change', renderCalls);
    $('#refreshAdmin').addEventListener('click', loadAdmin);
    $$('[data-page]').forEach(button => button.addEventListener('click', () => showPage(button.dataset.page)));
    $$('[data-page-link]').forEach(button => button.addEventListener('click', () => showPage(button.dataset.pageLink)));
    $$('[data-refresh]').forEach(button => button.addEventListener('click', async () => {
      try { await busy(button, loadAll); toast('Dashboard refreshed.'); } catch (error) { toast(error.message, true); }
    }));
    $$('.call-list').forEach(list => list.addEventListener('click', event => {
      const row = event.target.closest('[data-call-id]');
      if (row) openCall(row.dataset.callId);
    }));
    $$('[data-close-dialog]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
    $$('dialog').forEach(dialog => dialog.addEventListener('click', event => {
      const rect = dialog.getBoundingClientRect();
      const inside = event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
      if (!inside) dialog.close();
    }));
    $('#adminBusinesses').addEventListener('click', event => {
      const button = event.target.closest('[data-admin-save]');
      if (button) saveAdminRow(button.closest('[data-business-id]'), button);
    });
  }

  async function boot() {
    bindEvents();
    if (nativeShell) {
      $$('a[target="_blank"][href^="/"]').forEach(link => {
        link.href = `${API_BASE}${link.getAttribute('href')}`;
      });
    }
    try {
      state.config = await api('/api/public/config');
      $('#trialDays').textContent = state.config.trial_days || 14;
    } catch (_) { state.config = { trial_days: 14 }; }

    const resetToken = new URLSearchParams(location.search).get('reset');
    if (resetToken) {
      $('#requestResetForm').classList.add('hidden');
      $('#finishResetForm').classList.remove('hidden');
      $('#resetTitle').textContent = 'Choose a new password';
      $('#resetIntro').textContent = 'Use at least 10 characters for a secure password.';
      showAuth('reset');
      return;
    }

    if (!state.token) { showAuth('login'); return; }
    try {
      const me = await api('/api/me');
      state.user = me.user;
      state.business = me.business;
      showApp();
      await loadAll();
    } catch (_) { signOut(false); }
  }

  if ('serviceWorker' in navigator && !nativeShell) navigator.serviceWorker.register('/sw.js').catch(() => {});
  boot();
})();
