/* Manual finance controls use the case command adapter and never store another ledger. */
(() => {
  const money = (cents) => cents === null ? 'Not known' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
  const sourceName = (source, index = 0) => {
    const bankLabel = typeof window !== 'undefined' ? window.StillHerePlaidControls?.labelForSource(source.id) : null;
    const label = bankLabel || (source.id === 'cash_demo_001' ? 'Sample cash on hand' : `${source.type === 'cash' ? 'Cash on hand' : source.type === 'received_assistance' ? 'Received assistance' : 'Account'}${index ? ` ${index + 1}` : ''}`);
    return `${label}${source.accessible ? '' : ' (unavailable)'}`;
  };
  const categories = { food: 'Food and water', lodging: 'Temporary lodging', transport: 'Transportation', recovery: 'Recovery costs', health: 'Health', other: 'Other' };
  const stages = { discovered: 'Found a possible program', eligibility_unknown: 'Eligibility not known', eligibility_checked: 'Eligibility checked', preparing: 'Preparing', applied: 'Applied', approved: 'Approved, not received', received: 'Received', denied: 'Denied', appeal: 'Appealing' };

  function parseMoney(value, allowUnknown = false) {
    const clean = String(value).trim();
    if (!clean && allowUnknown) return null;
    if (!/^\d+(\.\d{1,2})?$/.test(clean)) throw new TypeError('Enter a dollar amount with up to two decimal places, such as 18.50.');
    const [whole, fraction = ''] = clean.split('.');
    const cents = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
    if (!Number.isSafeInteger(cents) || cents < 0) throw new TypeError('That amount is outside the supported range.');
    return cents;
  }

  function buildUpdate(ledger, fields, eventId) {
    const update = { event_id: eventId, effective_date: fields.date };
    const amount = ['aid', 'commitment'].includes(fields.mode) ? parseMoney(fields.amount, true) : ['undo', 'access'].includes(fields.mode) ? null : parseMoney(fields.amount);
    const source = ledger.money_sources.find((item) => item.id === fields.source);
    if (fields.mode === 'balance') {
      if (fields.source === 'new') return { ...update, operation: 'upsert_money_source', record: { id: `source_${eventId}`, type: fields.source_type, balance_cents: amount, currency: 'USD', accessible: true, restrictions: fields.restrictions === 'unknown' ? null : fields.restrictions ? [fields.restrictions] : [], as_of: fields.date } };
      if (!source) throw new TypeError('Choose a money source.');
      return { ...update, operation: 'refresh_balance', money_source_id: source.id, balance_cents: amount, reflected_event_ids: ledger.actual_events.filter((event) => [event.money_source_id, event.destination_source_id].includes(source.id)).map((event) => event.id) };
    }
    if (fields.mode === 'access') {
      if (!source) throw new TypeError('Choose a money source.');
      return { ...update, operation: 'set_source_access', money_source_id: source.id, accessible: !source.accessible, restrictions: source.restrictions };
    }
    if (fields.mode === 'expense' || fields.mode === 'receipt') {
      if (!amount) throw new TypeError('Enter an amount greater than zero.');
      if (!source) throw new TypeError('Choose a money source.');
      return { ...update, operation: `record_${fields.mode}`, money_source_id: source.id, amount_cents: amount, balance_effect: fields.balance_effect,
        ...(fields.mode === 'expense' ? { category: fields.category, ...(fields.commitment ? { commitment_id: fields.commitment } : { unplanned: true }) } : fields.aid ? { aid_id: fields.aid } : {}) };
    }
    if (fields.mode === 'commitment') {
      const original = ledger.expense_commitments.find((item) => item.id === fields.record);
      const record = original ? structuredClone(original) : { id: `cost_${eventId}`, essential: true };
      for (const key of ['fulfilled_by_date', 'date', 'day', 'start_date', 'end_date', 'start_day', 'end_day']) delete record[key];
      Object.assign(record, { category: fields.category, amount_cents: amount }, fields.frequency === 'daily' ? { start_date: fields.date, end_date: fields.end_date } : { date: fields.date });
      return { ...update, operation: 'upsert_commitment', record };
    }
    if (fields.mode === 'aid') {
      const original = (ledger.aid || []).find((item) => item.id === fields.record);
      const record = original ? structuredClone(original) : { id: `aid_${eventId}` };
      delete record.actual_receipt_id;
      Object.assign(record, { stage: fields.stage, amount_cents: amount, restrictions: fields.restrictions === 'keep' ? original.restrictions : fields.restrictions === 'unknown' ? null : fields.restrictions ? [fields.restrictions] : [] });
      return { ...update, operation: 'upsert_aid', record };
    }
    if (fields.mode === 'undo') {
      const event = ledger.actual_events.find((item) => item.id === fields.record);
      return event ? { ...update, operation: 'reverse_event', original_event_id: event.id, balance_effect: 'adjust_source' }
        : { ...update, operation: 'reverse_record_update', original_update_id: fields.record };
    }
    throw new TypeError('Choose a supported finance action.');
  }

  function describe(update, ledger) {
    const source = ledger.money_sources.find((item) => item.id === update.money_source_id);
    const label = source ? sourceName(source, ledger.money_sources.indexOf(source)) : '';
    if (update.operation === 'refresh_balance') return `Set ${label} to ${money(update.balance_cents)} as of ${update.effective_date}. This balance already includes all ${update.reflected_event_ids.length} recorded transactions affecting this source.`;
    if (update.operation === 'upsert_money_source') return `Add ${money(update.record.balance_cents)} of available money as of ${update.effective_date}. This must be a separate source, not money already listed.`;
    if (update.operation === 'record_expense' || update.operation === 'record_receipt') return `${update.operation === 'record_expense' ? 'Record spending of' : 'Record received money of'} ${money(update.amount_cents)} on ${update.effective_date} in ${label}. ${update.balance_effect === 'already_reflected' ? 'The current balance already includes this, so it will stay the same.' : 'The current balance will change by this amount.'} ${update.commitment_id ? 'This will count toward the selected planned cost.' : update.operation === 'record_expense' ? 'This is additional spending outside the planned costs.' : update.aid_id ? 'This receipt will mark the selected aid received.' : ''}`;
    if (update.operation === 'upsert_commitment') return `Set ${categories[update.record.category] || update.record.category} to ${money(update.record.amount_cents)} ${update.record.start_date ? `per day from ${update.record.start_date} through ${update.record.end_date}` : `on ${update.record.date}`}. Existing recorded spending stays linked.`;
    if (update.operation === 'upsert_aid') return `Track aid as ${stages[update.record.stage]} with an amount of ${money(update.record.amount_cents)}. This edit does not add money to your balance.`;
    if (update.operation === 'set_source_access') return `${update.accessible ? 'Make' : 'Mark'} ${label} ${update.accessible ? 'available again' : 'unavailable'}. Its recorded balance stays the same.`;
    return 'Undo this entry and restore its recorded financial effect. The original entry will remain in the history. Later changes may need reconciliation before this can be undone.';
  }

  function mount({ service, onChange }) {
    const root = document.querySelector('#finance-controls');
    root.innerHTML = `<div class="finance-actions" aria-label="Update the demo budget"><button class="button button-secondary" data-finance-edit="balance">Update money</button><button class="button button-secondary" data-finance-edit="expense">Add spending</button><button class="button button-secondary" data-finance-edit="receipt">Money received</button></div>
      <p class="finance-save-status" id="finance-save-status" role="status">Changes save to this device’s demo case.</p>
      <details class="finance-records"><summary>Money sources, aid &amp; recent entries</summary><div id="finance-source-list"></div><div class="finance-record-heading"><h3>Aid you’re tracking</h3><button class="quiet-link" data-finance-edit="aid">Add aid</button></div><div id="finance-aid-list"></div><h3>Recent entries</h3><div id="finance-history"></div></details>
      <dialog class="finance-editor" id="finance-editor" aria-labelledby="finance-editor-title"><form id="finance-entry-form"><div class="finance-panel-heading"><h2 id="finance-editor-title">Update money</h2><button type="button" class="quiet-link" id="finance-editor-close" aria-label="Close editor">Close</button></div><p class="finance-editor-note">Local demo only. Do not enter account or identity numbers.</p><div id="finance-edit-fields">
      <label data-field="source">Money source<select name="source"></select></label>
      <label data-field="source_type">Source type<select name="source_type"><option value="cash">Cash on hand</option><option value="account">Account</option><option value="received_assistance">Received assistance</option></select></label>
      <label data-field="amount">Amount in dollars<input name="amount" type="text" inputmode="decimal" autocomplete="off" placeholder="18.50"><small id="finance-amount-help">Enter the amount in dollars.</small></label>
      <label data-field="date">Date<input name="date" type="date" required></label>
      <label data-field="category">Category<select name="category"></select></label>
      <label data-field="commitment">Count toward a planned cost<select name="commitment"></select></label>
      <label data-field="aid">Link to tracked aid<select name="aid"></select></label>
      <label data-field="balance_effect">Does the current balance already include this?<select name="balance_effect"><option value="adjust_source">No — update the balance</option><option value="already_reflected">Yes — leave the balance as it is</option></select></label>
      <label data-field="frequency">How often?<select name="frequency"><option value="once">Once</option><option value="daily">Every day</option></select></label>
      <label data-field="end_date">Last day<input name="end_date" type="date"></label>
      <label data-field="stage">Application progress<select name="stage"></select></label>
      <label data-field="restrictions">What can this money pay for?<select name="restrictions"><option value="unknown">Not known yet</option><option value="">No restrictions</option><option value="food">Food only</option><option value="lodging">Lodging only</option><option value="transport">Transport only</option></select></label></div>
      <div class="finance-review is-hidden" id="finance-review"><h3>Check this before saving</h3><p id="finance-review-copy"></p><button type="button" class="quiet-link" id="finance-review-back">Edit entry</button></div><p class="finance-editor-error" id="finance-editor-error" role="alert"></p><button class="button button-primary" id="finance-entry-submit" type="submit">Review entry</button><a class="finance-dialog-emergency" href="tel:911">In immediate danger? Call 911</a></form></dialog>`;
    const dialog = root.querySelector('#finance-editor');
    const form = root.querySelector('form');
    const field = (name) => form.elements.namedItem(name);
    const error = root.querySelector('#finance-editor-error');
    let mode;
    let recordId;
    let pending;
    let returnFocus;
    const newId = () => `p2_finance_${window.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2)}`}`;
    const options = (name, rows) => field(name).replaceChildren(...rows.map(([value, text]) => { const option = document.createElement('option'); option.value = value; option.textContent = text; return option; }));
    const show = (name, visible) => { const label = form.querySelector(`[data-field="${name}"]`); label.classList.toggle('is-hidden', !visible); field(name).disabled = !visible; };
    function fieldsChanged() {
      show('source_type', mode === 'balance' && field('source').value === 'new');
      show('restrictions', mode === 'aid' || (mode === 'balance' && field('source').value === 'new'));
      show('end_date', mode === 'commitment' && field('frequency').value === 'daily');
      if (mode === 'expense') {
        const commitments = service.readCase().finance.ledger.expense_commitments.filter((item) => item.category === field('category').value);
        options('commitment', [['', 'Additional spending outside my plan'], ...commitments.map((item) => [item.id, `${categories[item.category] || item.category} · ${money(item.amount_cents)}`])]);
      }
    }
    function open(nextMode, id = '') {
      returnFocus = document.activeElement;
      mode = nextMode; recordId = id; pending = null;
      form.reset(); error.textContent = '';
      field('restrictions').querySelector('option[value="keep"]')?.remove();
      root.querySelector('#finance-edit-fields').classList.remove('is-hidden');
      root.querySelector('#finance-review').classList.add('is-hidden');
      root.querySelector('#finance-entry-submit').textContent = 'Review entry';
      const ledger = service.readCase().finance.ledger;
      options('source', [...ledger.money_sources.map((item, index) => [item.id, sourceName(item, index)]), ...(mode === 'balance' ? [['new', 'Add a separate money source']] : [])]);
      options('category', Object.entries(categories));
      options('aid', [['', 'Other money received'], ...(ledger.aid || []).filter((item) => item.stage !== 'received').map((item, index) => [item.id, `Aid ${index + 1} · ${stages[item.stage]}`])]);
      options('stage', Object.entries(stages).filter(([stage]) => stage !== 'received'));
      field('date').value = '2026-10-10'; field('end_date').value = '2026-10-23';
      const visible = { balance: ['source', 'amount', 'date'], expense: ['source', 'amount', 'date', 'category', 'commitment', 'balance_effect'], receipt: ['source', 'amount', 'date', 'aid', 'balance_effect'], commitment: ['amount', 'date', 'category', 'frequency'], aid: ['amount', 'date', 'stage', 'restrictions'], access: ['source', 'date'], undo: ['date'] }[mode];
      for (const name of ['source', 'source_type', 'amount', 'date', 'category', 'commitment', 'aid', 'balance_effect', 'frequency', 'end_date', 'stage', 'restrictions']) show(name, visible.includes(name));
      const titles = { balance: 'Update available money', expense: 'Add spending', receipt: 'Record money received', commitment: 'Edit a planned cost', aid: 'Track aid progress', access: 'Change money access', undo: 'Undo an entry' };
      root.querySelector('#finance-editor-title').textContent = titles[mode];
      root.querySelector('#finance-amount-help').textContent = ['aid', 'commitment'].includes(mode) ? 'Leave blank if the amount is not known yet.' : mode === 'balance' ? 'Enter what is available now, including transactions already listed.' : 'Enter the amount in dollars.';
      if (mode === 'balance') field('amount').value = ledger.money_sources[0]?.balance_cents === null ? '' : String((ledger.money_sources[0]?.balance_cents || 0) / 100);
      if (mode === 'access') field('source').value = id;
      if (mode === 'commitment' && id) {
        const item = ledger.expense_commitments.find((entry) => entry.id === id);
        field('amount').value = item.amount_cents === null ? '' : String(item.amount_cents / 100);
        field('category').value = item.category;
        field('frequency').value = item.start_date || item.start_day ? 'daily' : 'once';
        field('date').value = item.date || item.start_date || `2026-10-${String(9 + (item.day || item.start_day || 1)).padStart(2, '0')}`;
        field('end_date').value = item.end_date || `2026-10-${String(9 + (item.end_day || 14)).padStart(2, '0')}`;
      }
      if (mode === 'aid' && id) {
        const item = ledger.aid.find((entry) => entry.id === id);
        field('amount').value = item.amount_cents === null ? '' : String(item.amount_cents / 100);
        if (item.stage === 'received') options('stage', [['received', stages.received]]);
        field('stage').value = item.stage;
        if (item.restrictions?.length > 1) { const option = document.createElement('option'); option.value = 'keep'; option.textContent = `Keep current restrictions: ${item.restrictions.join(', ')}`; field('restrictions').append(option); }
        field('restrictions').value = item.restrictions === null || item.restrictions === undefined ? 'unknown' : item.restrictions[0] || '';
        if (item.restrictions?.length > 1) field('restrictions').value = 'keep';
      }
      fieldsChanged(); dialog.showModal();
    }
    function row(text, action, label, id, kind) {
      const node = document.createElement('div'); node.className = 'finance-record-row';
      const copy = document.createElement('span'); copy.textContent = text; node.append(copy);
      if (action) { const button = document.createElement('button'); button.type = 'button'; button.className = 'quiet-link'; button.dataset.financeEdit = action; button.dataset.record = id; button.textContent = label; if (kind) button.setAttribute('aria-label', `${label} ${kind}`); node.append(button); }
      return node;
    }
    function render() {
      const ledger = service.readCase().finance.ledger;
      root.querySelector('#finance-source-list').replaceChildren(...ledger.money_sources.map((item, index) => row(`${sourceName(item, index)} · ${money(item.balance_cents)}${item.restrictions === null ? ' · restrictions unknown' : item.restrictions.length ? ` · ${item.restrictions.join(', ')} only` : ''}`, 'access', item.accessible ? 'Mark unavailable' : 'Make available', item.id)));
      root.querySelector('#finance-aid-list').replaceChildren(...(ledger.aid || []).map((item, index) => row(`Aid ${index + 1} · ${stages[item.stage]} · ${money(item.amount_cents)}`, 'aid', 'Edit', item.id, `aid ${index + 1}`)));
      if (!ledger.aid?.length) root.querySelector('#finance-aid-list').textContent = 'No aid recorded. Expected aid will not increase available money.';
      const entries = [...ledger.actual_events.map((item) => ({ ...item, isEvent: true })), ...(ledger.record_updates || [])].reverse().sort((a, b) => b.effective_date.localeCompare(a.effective_date)).slice(0, 8);
      root.querySelector('#finance-history').replaceChildren(...entries.map((item) => row(`${item.effective_date} · ${item.isEvent ? item.kind : item.operation.replaceAll('_', ' ')}${item.amount_cents !== undefined ? ` · ${money(item.amount_cents)}` : ''}${item.reversed_by ? ' · undone' : ''}`, !item.reversed_by && item.kind !== 'correction' && item.operation !== 'reverse_record_update' ? 'undo' : null, 'Undo', item.id)));
      if (!entries.length) root.querySelector('#finance-history').textContent = 'No entries yet.';
      const costs = document.querySelector('#finance-costs');
      costs.replaceChildren(...ledger.expense_commitments.map((item) => row(`${categories[item.category] || item.category} · ${money(item.amount_cents)}${item.start_day || item.start_date ? ' / day' : ' once'}`, 'commitment', 'Edit', item.id, categories[item.category] || item.category)), row('Add another planned cost', 'commitment', 'Add', ''));
    }
    document.addEventListener('click', (event) => { const button = event.target.closest('[data-finance-edit]'); if (button) open(button.dataset.financeEdit, button.dataset.record); });
    const close = () => { dialog.close(); returnFocus?.focus(); };
    root.querySelector('#finance-editor-close').addEventListener('click', close);
    dialog.addEventListener('cancel', () => { pending = null; });
    form.addEventListener('change', (event) => {
      if (event.target.name === 'source' && mode === 'balance') {
        const source = service.readCase().finance.ledger.money_sources.find((item) => item.id === field('source').value);
        field('amount').value = source?.balance_cents === null || !source ? '' : String(source.balance_cents / 100);
      }
      if (['source', 'frequency', 'category'].includes(event.target.name)) fieldsChanged();
    });
    root.querySelector('#finance-review-back').addEventListener('click', () => {
      pending = null; error.textContent = '';
      root.querySelector('#finance-edit-fields').classList.remove('is-hidden');
      root.querySelector('#finance-review').classList.add('is-hidden');
      root.querySelector('#finance-entry-submit').textContent = 'Review entry';
    });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!dialog.open) return;
      error.textContent = '';
      if (!pending) {
        try {
          const snapshot = service.readCase();
          const id = newId();
          const fields = Object.fromEntries(new FormData(form));
          const update = buildUpdate(snapshot.finance.ledger, { ...fields, mode, record: recordId }, id);
          const preview = window.StillHereFinance.apply_financial_update(snapshot.finance.ledger, update);
          if (preview.status !== 'applied') throw new TypeError(preview.issues[0]?.message || 'Review the entry before continuing.');
          const { event_id, ...payload } = update;
          pending = { contract_version: '0.1', case_id: snapshot.case_id, event_id, expected_case_version: snapshot.case_version, occurred_at: new Date().toISOString(), channel: 'dashboard', type: 'finance.update', payload };
          root.querySelector('#finance-review-copy').textContent = describe(update, snapshot.finance.ledger);
          root.querySelector('#finance-edit-fields').classList.add('is-hidden');
          root.querySelector('#finance-review').classList.remove('is-hidden');
          root.querySelector('#finance-entry-submit').textContent = 'Confirm & save';
        } catch (problem) { error.textContent = problem.message; }
        return;
      }
      const result = service.submit(pending);
      if (!['applied', 'already_applied'].includes(result.status)) { error.textContent = result.status === 'conflict' ? 'The case changed while this entry was open. Choose Edit entry to review it against the latest case before saving again.' : result.issues[0]?.message || 'The entry could not be saved.'; return; }
      pending = null; close();
      root.querySelector('#finance-save-status').textContent = 'Saved on this device. The demo forecast has been updated.';
      onChange();
      if (!returnFocus?.isConnected) root.querySelector('[data-finance-edit]').focus();
    });
    return { render };
  }

  const api = Object.freeze({ parseMoney, buildUpdate, describe, mount });
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.StillHereFinanceControls = api;
})();
// Built by Raneem Mousa
