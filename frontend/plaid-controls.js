/* Optional Sandbox linking; reviewed balances use the same finance command adapter. */
(() => {
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const dollars = (value) => Number.isSafeInteger(value) ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value / 100) : 'Unavailable';
  const displayTime = (value) => value ? new Date(value).toLocaleString() : 'Not fetched';
  const accountLabels = new Map();
  const accountName = (account) => `${account.name}${account.mask ? ` · ending ${account.mask}` : ''}`;
  function rememberAccounts(value) {
    value.accounts.forEach((account) => accountLabels.set(account.id, accountName(account)));
  }
  let sdkPromise;
  function loadLink() {
    if (window.Plaid) return Promise.resolve();
    if (!sdkPromise) sdkPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';
      script.onload = resolve;
      script.onerror = () => { script.remove(); sdkPromise = null; reject(new Error('Plaid Link could not load. Check your connection and try again.')); };
      document.head.append(script);
    });
    return sdkPromise;
  }
  function mount({ service, onChange }) {
    const root = document.querySelector('#plaid-controls');
    const isLocalServer = location.protocol === 'http:' && location.hostname === '127.0.0.1';
    let state = null;
    let busy = false;
    let message = '';
    let pendingExchange = null;
    let reviewed = null;
    let chosenAccount = null;
    let checkingStatus = null;
    let linkHandler;
    let returnFocus;
    root.innerHTML = `<details class="finance-panel plaid-panel" id="plaid-panel"><summary>Connect a test bank <span class="plaid-badge">PLAID SANDBOX</span></summary><p class="plaid-copy">Optional, read-only access to synthetic checking or savings accounts. Manual money entry always stays available.</p><div id="plaid-content"></div></details>
      <dialog class="finance-editor" id="plaid-review-dialog" aria-labelledby="plaid-review-title"><form id="plaid-balance-form"><div class="finance-panel-heading"><h2 id="plaid-review-title">Review test-bank balance</h2><button type="button" class="quiet-link" data-plaid-action="close-review">Close</button></div><p class="finance-editor-note">Each test account has its own budget entry. Reviewing it again updates that same account.</p><p class="finance-review" id="plaid-balance-description"></p><label class="plaid-consent"><input type="checkbox" name="consent" required><span>I checked this balance. For a new account, these funds are separate from money already listed, accessible, and unrestricted. An updated balance includes all recorded transactions for this account.</span></label><p id="plaid-review-error" class="finance-editor-error" role="alert"></p><button class="button button-primary" type="submit">Review budget change</button><a class="finance-dialog-emergency" href="tel:911">In immediate danger? Call 911</a></form></dialog>`;
    const content = root.querySelector('#plaid-content');
    const dialog = root.querySelector('#plaid-review-dialog');
    const form = root.querySelector('#plaid-balance-form');
    const reviewError = root.querySelector('#plaid-review-error');
    function render() {
      const disabled = busy ? 'disabled' : '';
      const budgetSources = new Map(service.readCase().finance.ledger.money_sources.map((source) => [source.id, source]));
      if (!isLocalServer) {
        content.innerHTML = '<p class="plaid-copy">Start the private local connector with <code>npm run plaid:sandbox</code>, then open the address it prints. Keep Sandbox keys in <code>.env.plaid</code>.</p>';
        return;
      }
      content.innerHTML = `<p class="plaid-status" role="status">${escape(message || (state?.connected ? 'A test bank is connected to this local session.' : state?.configured ? 'Ready to connect a test bank.' : 'Add Sandbox keys to .env.plaid, then restart the local connector.'))}</p>
        <div class="plaid-actions">${state?.connected ? `<button class="button button-secondary" data-plaid-action="refresh" ${disabled}>Refresh bank data</button><button class="quiet-link" data-plaid-action="disconnect" ${disabled}>Disconnect test bank</button>` : `<button class="button button-secondary" data-plaid-action="${pendingExchange ? 'retry-exchange' : 'connect'}" ${!state?.configured || busy ? 'disabled' : ''}>${pendingExchange ? 'Retry completed bank connection' : 'Connect a test bank'}</button>${pendingExchange ? `<button class="quiet-link" data-plaid-action="restart-link" ${disabled}>Start connection again</button>` : ''}<button class="quiet-link" data-plaid-action="status" ${disabled}>Check setup</button>`}</div>
        ${state?.connected ? `<p class="plaid-copy">Balances fetched: ${escape(displayTime(state.balances_fetched_at))}. A copied balance stays in the budget after disconnecting. Review it manually when it becomes outdated.</p>
          ${state.accounts.map((account) => {
            const source = budgetSources.get(account.id);
            return `<div class="plaid-account"><div><strong>${escape(accountName(account))}</strong><span>Available at test bank: ${account.currency === 'USD' ? dollars(account.available_cents) : escape(account.currency || 'Unknown currency')}</span><span>${source ? `Saved in budget: ${dollars(source.balance_cents)}${source.accessible ? '' : ' · marked unavailable'}${source.restrictions === null ? ' · restrictions unknown' : source.restrictions.length ? ' · restricted' : ''}` : 'Not yet added to budget'}</span></div><button class="quiet-link" data-plaid-account="${escape(account.id)}" ${busy || account.currency !== 'USD' || account.available_cents === null || account.available_cents < 0 ? 'disabled' : ''}>${source ? 'Review balance update' : 'Review for budget'}</button></div>`;
          }).join('') || '<p class="plaid-copy">No eligible checking or savings balances have been fetched. Refresh bank data to try again.</p>'}
          <details class="plaid-history"><summary>Recent test transactions</summary><p class="plaid-copy">Fetched ${escape(displayTime(state.transactions_fetched_at))}. History is for review and is not deducted again from the balance. Deposits are not automatically treated as aid.</p>
            ${state.transactions.slice(0, 20).map((record) => `<div class="plaid-transaction"><span><strong>${escape(record.name)}</strong><small>${escape(record.date)} · ${record.pending ? 'Pending' : 'Posted'}</small></span><span>${record.currency === 'USD' && record.amount_cents !== null ? `${record.amount_cents < 0 ? 'In ' : 'Out '}${dollars(Math.abs(record.amount_cents))}` : 'Amount unavailable'}</span></div>`).join('') || `<p class="plaid-copy">${state.transactions_ready ? 'No transactions were returned for the selected accounts.' : 'Transaction history may still be preparing. Refresh again shortly.'}</p>`}</details>` : ''}`;
    }
    async function api(route, payload) {
      const response = await fetch(`/api/plaid/${route}`, {
        method: payload === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: payload === undefined ? {} : { 'Content-Type': 'application/json', 'X-StillHere-CSRF': state?.csrf || '' },
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) })
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error?.message || 'The local Plaid connector could not finish this request.');
      return value;
    }
    async function status() {
      if (!isLocalServer) { render(); return; }
      if (checkingStatus) return checkingStatus;
      checkingStatus = (async () => {
        try { state = await api('status'); rememberAccounts(state); onChange(); }
        catch { message = 'The Plaid connector is unavailable. Start it with npm run plaid:sandbox; manual entry still works.'; }
        finally { checkingStatus = null; render(); }
      })();
      return checkingStatus;
    }
    async function refresh() { state = await api('refresh', {}); rememberAccounts(state); onChange(); message = 'Test-bank data fetched. Review each account before changing its budget balance.'; }
    async function exchange() {
      state = await api('exchange', { public_token: pendingExchange });
      pendingExchange = null;
      await refresh();
    }
    async function connect() {
      linkHandler?.destroy();
      linkHandler = null;
      const [token] = await Promise.all([api('link-token', {}), loadLink()]);
      linkHandler = window.Plaid.create({
        token: token.link_token,
        onSuccess: async (publicToken) => {
          pendingExchange = publicToken;
          busy = true;
          render();
          try { await exchange(); }
          catch (error) { message = error.message; await status(); if (state?.connected) pendingExchange = null; }
          finally { busy = false; render(); linkHandler?.destroy(); linkHandler = null; root.querySelector('[data-plaid-action]')?.focus(); }
        },
        onExit: (error) => { busy = false; message = error ? 'Plaid Link did not complete. Retry the connection when ready.' : 'Connection canceled. Manual entry is still available.'; render(); linkHandler?.destroy(); linkHandler = null; root.querySelector('[data-plaid-action]')?.focus(); }
      });
      linkHandler.open();
    }
    function openReview(id) {
      chosenAccount = state.accounts.find((account) => account.id === id);
      if (!chosenAccount || chosenAccount.currency !== 'USD' || !Number.isSafeInteger(chosenAccount.available_cents) || chosenAccount.available_cents < 0) return;
      returnFocus = document.activeElement;
      reviewed = null;
      form.reset();
      reviewError.textContent = '';
      const source = service.readCase().finance.ledger.money_sources.find((item) => item.id === id);
      root.querySelector('#plaid-balance-description').textContent = `${accountName(chosenAccount)}: ${dollars(chosenAccount.available_cents)} available. Fetched ${displayTime(chosenAccount.fetched_at)}. ${source ? `Update this account’s saved ${dollars(source.balance_cents)} balance.` : 'Add this account as a separate budget entry. Check that it is not already recorded manually.'}`;
      form.querySelector('[type="submit"]').textContent = 'Review budget change';
      dialog.showModal();
      form.elements.consent.focus();
    }
    function closeReview() { dialog.close(); reviewed = null; chosenAccount = null; returnFocus?.focus(); }
    form.addEventListener('change', () => {
      reviewed = null;
      form.querySelector('[type="submit"]').textContent = 'Review budget change';
    });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!dialog.open || !chosenAccount) return;
      reviewError.textContent = '';
      if (!reviewed) {
        const snapshot = service.readCase();
        const dateParts = new Intl.DateTimeFormat('en-US', { timeZone: snapshot.time_zone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(chosenAccount.fetched_at));
        const part = (type) => dateParts.find((entry) => entry.type === type).value;
        const date = `${part('year')}-${part('month')}-${part('day')}`;
        if (date !== '2026-10-10') { reviewError.textContent = 'This prototype budget starts October 10, 2026. Keep this newer bank balance separate until P1 supports planning from the current date.'; return; }
        // An account can only refresh its own entry; another account is separate money.
        const source = snapshot.finance.ledger.money_sources.find((item) => item.id === chosenAccount.id);
        if (source && source.type !== 'account') { reviewError.textContent = 'This saved entry needs reconciliation before it can be linked to a test account.'; return; }
        const eventId = `plaid_${window.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(16).slice(2)}`}`;
        const payload = source ? { operation: 'refresh_balance', money_source_id: source.id, balance_cents: chosenAccount.available_cents, reflected_event_ids: snapshot.finance.ledger.actual_events.filter((record) => [record.money_source_id, record.destination_source_id].includes(source.id)).map((record) => record.id), effective_date: date }
          : { operation: 'upsert_money_source', record: { id: chosenAccount.id, type: 'account', balance_cents: chosenAccount.available_cents, currency: 'USD', accessible: true, restrictions: [], as_of: date }, effective_date: date };
        let before;
        let after;
        try {
          const preview = window.StillHereFinance.apply_financial_update(snapshot.finance.ledger, { ...payload, event_id: eventId });
          if (preview.status !== 'applied') throw new Error(preview.issues?.[0]?.message || 'This balance needs review.');
          const opening = (ledger) => window.StillHereFinance.forecast_finances({ ledger, start_date: '2026-10-10', case_time_zone: snapshot.time_zone, input_case_version: snapshot.case_version, scenarios: [] }).baseline.opening_cents;
          before = opening(snapshot.finance.ledger);
          after = opening(preview.ledger);
        } catch (error) { reviewError.textContent = error.message; return; }
        reviewed = { contract_version: '0.1', case_id: snapshot.case_id, expected_case_version: snapshot.case_version, event_id: eventId, occurred_at: new Date().toISOString(), channel: 'dashboard', type: 'finance.update', payload };
        root.querySelector('#plaid-balance-description').textContent = `${source ? 'Update' : 'Add'} ${accountName(chosenAccount)}${source ? ` from ${dollars(source.balance_cents)} to` : ' with'} ${dollars(chosenAccount.available_cents)}, as of ${date}. Available at start: ${dollars(before)} → ${dollars(after)}. ${source && (!source.accessible || source.restrictions === null || source.restrictions.length) ? 'This entry has access or use restrictions; only eligible funds enter the starting total.' : ''}`;
        form.querySelector('[type="submit"]').textContent = 'Confirm budget change';
        return;
      }
      const result = service.submit(reviewed);
      if (!['applied', 'already_applied'].includes(result.status)) {
        reviewError.textContent = result.issues?.[0]?.message || 'The balance was not saved.';
        if (result.status === 'conflict') { reviewed = null; form.querySelector('[type="submit"]').textContent = 'Review against latest budget'; }
        return;
      }
      const savedAccountName = accountName(chosenAccount);
      closeReview();
      message = `${savedAccountName} saved to this device’s budget. The forecast was refreshed.`;
      render();
      onChange();
    });
    root.addEventListener('click', async (event) => {
      const accountId = event.target.closest('[data-plaid-account]')?.dataset.plaidAccount;
      if (accountId && !busy) { openReview(accountId); return; }
      const action = event.target.closest('[data-plaid-action]')?.dataset.plaidAction;
      if (!action) return;
      if (action === 'close-review') { closeReview(); return; }
      if (busy) return;
      busy = true;
      message = '';
      render();
      try {
        if (action === 'status') await status();
        if (action === 'connect') { await connect(); return; }
        if (action === 'restart-link') { pendingExchange = null; await status(); message = 'Connection reset. Choose Connect a test bank when ready.'; }
        if (action === 'retry-exchange') await exchange();
        if (action === 'refresh') await refresh();
        if (action === 'disconnect') { state = await api('disconnect', {}); pendingExchange = null; message = 'Test bank disconnected. Previously copied balances remain as manual budget records.'; }
      } catch (error) { message = error.message; if (action === 'connect') { linkHandler?.destroy(); linkHandler = null; } await status(); }
      finally { if (action !== 'connect' || !linkHandler) busy = false; render(); }
    });
    dialog.addEventListener('cancel', () => { reviewed = null; chosenAccount = null; });
    root.querySelector('#plaid-panel').addEventListener('toggle', (event) => { if (event.target.open && !state) status(); });
    render();
    return Object.freeze({ render });
  }
  window.StillHerePlaidControls = Object.freeze({ mount, labelForSource: (id) => accountLabels.get(id) || null });
})();
// Built by Raneem Mousa
