/* Deterministic, dependency-free 14-day forecast engine. All money is integer USD cents. */
(() => {
  const DAY_COUNT = 14;
  const scenarios = [
    { id: 'baseline', label: 'No new support', description: 'No support or new aid is included.', support: [], receipts: [] },
    { id: 'coverage', label: 'Food and lodging, days 1–7', description: 'Example noncash coverage offsets food and lodging for the first seven days.', support: [{ categories: ['food', 'lodging'], start_day: 1, end_day: 7 }], receipts: [] },
    { id: 'aid_day_8', label: 'Coverage + aid on day 8', description: 'Conditional example: the same coverage, plus $500 if aid arrives on day 8.', support: [{ categories: ['food', 'lodging'], start_day: 1, end_day: 7 }], receipts: [{ amount_cents: 50000, day: 8 }] },
    { id: 'aid_day_12', label: 'Coverage + aid on day 12', description: 'Conditional example: the same coverage, plus $500 if aid arrives on day 12.', support: [{ categories: ['food', 'lodging'], start_day: 1, end_day: 7 }], receipts: [{ amount_cents: 50000, day: 12 }] }
  ];

  function dateAt(startDate, dayOffset) {
    const date = new Date(`${startDate}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() + dayOffset);
    return date.toISOString().slice(0, 10);
  }

  function validDate(value) {
    return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
  }

  function validCents(value) {
    return Number.isSafeInteger(value) && value >= 0;
  }

  function updateResult(status, ledger, changedRecordIds = [], reconciliationNotes = [], issues = []) {
    return { status, ledger, changed_record_ids: changedRecordIds, reconciliation_notes: reconciliationNotes, issues };
  }

  function stableJson(value) {
    if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
    if (value && typeof value === 'object') return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
    return JSON.stringify(value);
  }

  function validSchedule(record) {
    if (record.date) return validDate(record.date);
    if (record.start_date) return validDate(record.start_date) && validDate(record.end_date) && record.end_date >= record.start_date;
    if (record.day !== undefined) return Number.isInteger(record.day) && record.day >= 1 && record.day <= DAY_COUNT;
    return Number.isInteger(record.start_day) && Number.isInteger(record.end_day) && record.start_day >= 1 && record.end_day <= DAY_COUNT && record.end_day >= record.start_day;
  }

  function affectedSources(event) {
    return [event.money_source_id, event.destination_source_id].filter(Boolean);
  }

  function applyTransferOrReversal(ledger, update) {
    const fail = (code, message, status = 'needs_clarification') => updateResult(status, ledger, [], [], [{ code, message }]);
    if (typeof update.event_id !== 'string' || !update.event_id.trim() || !validDate(update.effective_date) || !['adjust_source', 'already_reflected'].includes(update.balance_effect)) return fail('invalid_update', 'Provide an event ID, date, and explicit balance effect.', 'rejected');
    const fingerprint = stableJson(update);
    const prior = ledger.actual_events.find((item) => item.id === update.event_id);
    if (prior) return prior.request_fingerprint === fingerprint ? updateResult('already_applied', ledger) : fail('event_id_reused', 'That event ID already describes another update.', 'rejected');
    if ((ledger.record_updates || []).some((item) => item.id === update.event_id)) return fail('event_id_reused', 'That event ID belongs to a record update.', 'rejected');
    const next = structuredClone(ledger);
    let event;
    let changedIds = [];
    if (update.operation === 'record_transfer') {
      if (!validCents(update.amount_cents) || update.amount_cents === 0 || update.money_source_id === update.destination_source_id) return fail('invalid_transfer', 'Choose distinct sources and a positive integer amount in cents.', 'rejected');
      const from = next.money_sources.find((item) => item.id === update.money_source_id);
      const to = next.money_sources.find((item) => item.id === update.destination_source_id);
      if (!from || !to || !validCents(from.balance_cents) || !validCents(to.balance_cents) || from.currency !== 'USD' || to.currency !== 'USD') return fail('unknown_transfer_balance', 'Confirm both USD sources and their current balances.');
      if (!Array.isArray(from.restrictions) || !Array.isArray(to.restrictions) || stableJson([...from.restrictions].sort()) !== stableJson([...to.restrictions].sort()) || from.expires_on !== to.expires_on || from.available_on !== to.available_on) return fail('transfer_restrictions', 'The destination must preserve the source funds’ known restrictions.');
      if (to.type === 'cash' && update.cash_on_hand_confirmed !== true) return fail('cash_confirmation_required', 'Confirm that the withdrawn cash is still on hand.');
      if (update.balance_effect === 'adjust_source') {
        if (!validCents(from.balance_cents - update.amount_cents) || !validCents(to.balance_cents + update.amount_cents)) return fail('balance_conflict', 'The transfer does not reconcile with these balances.');
        from.balance_cents -= update.amount_cents;
        to.balance_cents += update.amount_cents;
      }
      event = { id: update.event_id, kind: 'transfer', money_source_id: from.id, destination_source_id: to.id, amount_cents: update.amount_cents };
      changedIds = [from.id, to.id];
    } else {
      const original = next.actual_events.find((item) => item.id === update.original_event_id);
      if (!original || !['expense', 'receipt', 'transfer'].includes(original.kind)) return fail('unknown_original_event', 'Choose an expense, receipt, or transfer to reverse.');
      if (original.reversed_by) return fail('already_reversed', 'This transaction already has a reversal.');
      if (update.effective_date < original.effective_date) return fail('invalid_reversal_date', 'A reversal cannot precede the original event.', 'rejected');
      const sources = affectedSources(original).map((id) => next.money_sources.find((item) => item.id === id));
      if (sources.some((source) => !source || !validCents(source.balance_cents))) return fail('unknown_balance', 'Confirm the affected balances before reversing this transaction.');
      const deltas = original.kind === 'receipt' ? [-original.amount_cents] : original.kind === 'expense' ? [original.amount_cents] : [original.amount_cents, -original.amount_cents];
      if (update.balance_effect === 'adjust_source') {
        if (sources.some((source, index) => !validCents(source.balance_cents + deltas[index]))) return fail('balance_conflict', 'Reversing this transaction would contradict the current balances.');
        sources.forEach((source, index) => { source.balance_cents += deltas[index]; });
      }
      if (original.commitment_id) {
        const commitment = next.expense_commitments.find((item) => item.id === original.commitment_id);
        const fulfilled = commitment?.fulfilled_by_date?.[original.effective_date];
        if (!validCents(fulfilled) || fulfilled < original.amount_cents) return fail('commitment_conflict', 'The recorded fulfillment must be reconciled before this expense can be reversed.');
        commitment.fulfilled_by_date[original.effective_date] -= original.amount_cents;
        changedIds.push(commitment.id);
      }
      if (original.aid_id) {
        const aid = next.aid?.find((item) => item.id === original.aid_id);
        if (!aid || aid.actual_receipt_id !== original.id) return fail('aid_conflict', 'The aid record no longer matches this receipt.');
        aid.stage = original.aid_previous_stage || 'eligibility_unknown';
        delete aid.actual_receipt_id;
        changedIds.push(aid.id);
      }
      original.reversed_by = update.event_id;
      event = { id: update.event_id, kind: 'correction', original_event_id: original.id, amount_cents: original.amount_cents, money_source_id: original.money_source_id, ...(original.destination_source_id ? { destination_source_id: original.destination_source_id } : {}) };
      changedIds.push(original.id, ...sources.map((source) => source.id));
    }
    Object.assign(event, { effective_date: update.effective_date, balance_effect: update.balance_effect, request_fingerprint: fingerprint });
    next.actual_events.push(event);
    affectedSources(event).forEach((id) => {
      const source = next.money_sources.find((item) => item.id === id);
      source.reflected_event_ids = [...new Set([...(source.reflected_event_ids || []), event.id])];
    });
    return updateResult('applied', next, [event.id, ...new Set(changedIds)], ['Original transactions remain in the audit; transfers do not create household income.']);
  }

  function applyRecordUpdate(ledger, update) {
    const fail = (code, message, status = 'rejected') => updateResult(status, ledger, [], [], [{ code, message }]);
    if (typeof update.event_id !== 'string' || !update.event_id.trim() || !validDate(update.effective_date)) return fail('invalid_update', 'A stable event ID and effective date are required.');
    const fingerprint = stableJson(update);
    const prior = (ledger.record_updates || []).find((item) => item.id === update.event_id);
    if (prior) return prior.fingerprint === fingerprint ? updateResult('already_applied', ledger) : fail('event_id_reused', 'This event ID already describes a different update.');
    if (ledger.actual_events.some((item) => item.id === update.event_id)) return fail('event_id_reused', 'This event ID belongs to an actual transaction.');
    const next = structuredClone(ledger);
    let changedId;
    let before;
    let collectionName;
    if (update.operation === 'reverse_record_update') {
      const original = next.record_updates?.find((item) => item.id === update.original_update_id);
      if (!original || !original.collection || original.after === undefined || original.reversed_by || original.operation === 'reverse_record_update') return fail('unavailable_record_undo', 'Choose a reversible record update that has not already been undone.', 'needs_clarification');
      collectionName = original.collection;
      const index = next[collectionName].findIndex((item) => item.id === original.record_id);
      if (index < 0 || stableJson(next[collectionName][index]) !== stableJson(original.after) || update.effective_date < original.effective_date) return fail('record_changed', 'This record changed after that edit. Review the current values before correcting it.', 'needs_clarification');
      if (original.before === null && next.actual_events.some((event) => affectedSources(event).includes(original.record_id) || event.aid_id === original.record_id || event.commitment_id === original.record_id)) return fail('record_in_use', 'A transaction references this record; retain it and correct its fields instead.', 'needs_clarification');
      before = structuredClone(next[collectionName][index]);
      if (original.before === null) next[collectionName].splice(index, 1);
      else next[collectionName][index] = structuredClone(original.before);
      changedId = original.record_id;
      original.reversed_by = update.event_id;
    } else if (update.operation === 'set_source_access') {
      collectionName = 'money_sources';
      const source = next.money_sources.find((item) => item.id === update.money_source_id);
      if (!source) return fail('unknown_money_source', 'Choose an existing money source.', 'needs_clarification');
      if (typeof update.accessible !== 'boolean' || !(update.restrictions === null || (Array.isArray(update.restrictions) && update.restrictions.every((item) => typeof item === 'string' && item.trim())))) return fail('invalid_source_access', 'Provide accessibility and known category restrictions, or null when restrictions are unknown.');
      for (const key of ['available_on', 'expires_on']) if (update[key] !== undefined && update[key] !== null && !validDate(update[key])) return fail('invalid_source_date', 'Use a calendar date or null to clear availability/expiry.');
      if (stableJson(source.restrictions) !== stableJson(update.restrictions) && (!Array.isArray(update.evidence_ids) || !update.evidence_ids.length || update.evidence_ids.some((id) => typeof id !== 'string' || !id.trim()))) return fail('restriction_evidence_required', 'Provide the user-report or source-evidence reference supporting changed restrictions.', 'needs_clarification');
      before = structuredClone(source);
      source.accessible = update.accessible;
      source.restrictions = structuredClone(update.restrictions);
      if (update.evidence_ids) source.evidence_ids = [...update.evidence_ids];
      for (const key of ['available_on', 'expires_on']) {
        if (update[key] === null) delete source[key];
        else if (update[key] !== undefined) source[key] = update[key];
      }
      changedId = source.id;
    } else if (update.operation === 'refresh_balance') {
      collectionName = 'money_sources';
      const source = next.money_sources.find((item) => item.id === update.money_source_id);
      if (!source) return fail('unknown_money_source', 'Choose the source for this balance.', 'needs_clarification');
      if (!validCents(update.balance_cents) || !Array.isArray(update.reflected_event_ids)) return fail('invalid_balance', 'Provide a balance and the event IDs already included in it.');
      const known = ledger.actual_events.filter((event) => affectedSources(event).includes(source.id)).map((event) => event.id);
      if (update.effective_date < String(source.as_of || '').slice(0, 10) || known.some((id) => !update.reflected_event_ids.includes(id)) || update.reflected_event_ids.some((id) => !known.includes(id))) return fail('balance_conflict', 'The snapshot cannot be reconciled with recorded transactions. Confirm which transactions it includes.', 'needs_clarification');
      before = structuredClone(source);
      source.balance_cents = update.balance_cents;
      source.as_of = update.effective_date;
      source.reflected_event_ids = [...update.reflected_event_ids];
      changedId = source.id;
    } else {
      const collections = { upsert_money_source: 'money_sources', upsert_commitment: 'expense_commitments', upsert_aid: 'aid', upsert_support: 'support' };
      const collection = collections[update.operation];
      collectionName = collection;
      const record = update.record;
      if (!record || typeof record.id !== 'string' || !record.id.trim()) return fail('invalid_record', 'The record needs a stable ID.');
      if (collection === 'money_sources') {
        if (!(record.balance_cents === null || validCents(record.balance_cents)) || record.currency !== 'USD' || typeof record.accessible !== 'boolean' || !(record.restrictions === null || Array.isArray(record.restrictions)) || !validDate(record.as_of)) return fail('invalid_source', 'Provide a USD balance (or unknown), accessibility, restrictions (or unknown), and as-of date.');
        if (ledger.money_sources.some((item) => item.id === record.id)) return fail('use_balance_refresh', 'Use refresh_balance to reconcile an existing source.', 'needs_clarification');
      }
      if (collection === 'expense_commitments' && (!(record.amount_cents === null || validCents(record.amount_cents)) || typeof record.category !== 'string' || !record.category || !validSchedule(record))) return fail('invalid_commitment', 'An expense needs a category, dated schedule, and integer cents or an unknown amount.');
      if (collection === 'aid') {
        if (!['discovered', 'eligibility_unknown', 'eligibility_checked', 'preparing', 'applied', 'approved', 'received', 'denied', 'appeal'].includes(record.stage) || !(record.amount_cents === null || validCents(record.amount_cents))) return fail('invalid_aid', 'Provide a supported aid stage and amount or unknown.');
        if (record.stage === 'received' && !ledger.actual_events.some((event) => event.kind === 'receipt' && !event.reversed_by && event.aid_id === record.id)) return fail('receipt_required', 'Record the actual receipt before marking aid received.', 'needs_clarification');
      }
      if (collection === 'support' && (!['confirmed', 'hypothetical', 'ended'].includes(record.state) || !validSchedule(record) || !Array.isArray(record.categories) || record.categories.some((category) => typeof category !== 'string') || (record.amount_cents !== undefined && !validCents(record.amount_cents)) || (record.consumed_cents !== undefined && !validCents(record.consumed_cents)))) return fail('invalid_support', 'Support needs its state, covered categories, dates, and valid optional amount and consumption limits.');
      next[collection] ||= [];
      const index = next[collection].findIndex((item) => item.id === record.id);
      before = index >= 0 ? structuredClone(next[collection][index]) : null;
      const replacement = structuredClone(record);
      if (collection === 'expense_commitments') replacement.fulfilled_by_date = structuredClone(before?.fulfilled_by_date || {});
      if (index >= 0) next[collection][index] = replacement;
      else next[collection].push(replacement);
      changedId = record.id;
    }
    next.record_updates ||= [];
    next.record_updates.push({ id: update.event_id, effective_date: update.effective_date, operation: update.operation, record_id: changedId, collection: collectionName, before, after: structuredClone(next[collectionName].find((item) => item.id === changedId) || null), fingerprint });
    return updateResult('applied', next, [changedId], ['The previous record is retained in the update audit.']);
  }

  /*
   * Pure, local-domain update. The caller persists `ledger` only for `applied`.
   * `balance_effect` must be explicit for imported events so a refreshed balance
   * that already includes the event is never adjusted a second time.
   */
  function applyFinancialUpdate(ledger, update) {
    if (!ledger || !Array.isArray(ledger.money_sources) || !Array.isArray(ledger.actual_events) || !Array.isArray(ledger.expense_commitments)) {
      return updateResult('rejected', ledger, [], [], [{ code: 'invalid_ledger', message: 'A ledger with money_sources, actual_events, and expense_commitments is required.' }]);
    }
    if (update && ['record_transfer', 'reverse_event'].includes(update.operation)) return applyTransferOrReversal(ledger, update);
    if (update && ['set_source_access', 'reverse_record_update', 'refresh_balance', 'upsert_money_source', 'upsert_commitment', 'upsert_aid', 'upsert_support'].includes(update.operation)) return applyRecordUpdate(ledger, update);
    if (!update || !['record_expense', 'record_receipt'].includes(update.operation)) {
      return updateResult('rejected', ledger, [], [], [{ code: 'unsupported_operation', message: 'Choose record_expense or record_receipt.' }]);
    }
    const { event_id: eventId, money_source_id: sourceId, amount_cents: amount, effective_date: effectiveDate, balance_effect: balanceEffect } = update;
    const kind = update.operation.slice('record_'.length);
    if (typeof eventId !== 'string' || !eventId.trim() || typeof sourceId !== 'string' || !sourceId.trim() || !validCents(amount) || amount < 1 || !validDate(effectiveDate) || !['adjust_source', 'already_reflected'].includes(balanceEffect) || (kind === 'expense' && (typeof update.category !== 'string' || !update.category.trim()))) {
      return updateResult('rejected', ledger, [], [], [{ code: 'invalid_update', message: 'Provide an event ID, source ID, positive amount in cents, valid date, explicit balance effect, and an expense category when recording a cost.' }]);
    }

    if ((ledger.record_updates || []).some((item) => item.id === eventId)) return updateResult('rejected', ledger, [], [], [{ code: 'event_id_reused', message: 'This event ID belongs to a record update.' }]);
    const priorEvent = ledger.actual_events.find((event) => event.id === eventId);
    if (priorEvent) {
      const same = priorEvent.request_fingerprint ? priorEvent.request_fingerprint === stableJson(update) : priorEvent.kind === kind && priorEvent.money_source_id === sourceId && priorEvent.amount_cents === amount && priorEvent.effective_date === effectiveDate && priorEvent.balance_effect === balanceEffect && (priorEvent.category || null) === (update.category?.trim() || null) && (priorEvent.commitment_id || null) === (update.commitment_id || null) && (priorEvent.aid_id || null) === (update.aid_id || null);
      return same
        ? updateResult('already_applied', ledger, [eventId], ['This financial event was already recorded; the ledger was not changed.'])
        : updateResult('rejected', ledger, [], [], [{ code: 'event_id_reused', message: 'That event ID is already attached to a different financial update.' }]);
    }

    const sourceIndex = ledger.money_sources.findIndex((source) => source.id === sourceId);
    if (sourceIndex < 0) return updateResult('needs_clarification', ledger, [], [], [{ code: 'unknown_money_source', message: 'Choose which cash or account source this event affected.' }]);
    const source = ledger.money_sources[sourceIndex];
    if (source.currency !== 'USD') return updateResult('needs_clarification', ledger, [], [], [{ code: 'unsupported_currency', message: 'This finance demo accepts USD entries only.' }]);
    if (!validCents(source.balance_cents)) return updateResult('needs_clarification', ledger, [], [], [{ code: 'unknown_balance', message: 'The selected source has no known balance. Add or confirm its current balance first.' }]);

    if (kind === 'receipt' && update.aid_id) {
      if (!Array.isArray(ledger.aid) || !ledger.aid.some((aid) => aid.id === update.aid_id)) {
        return updateResult('needs_clarification', ledger, [], [], [{ code: 'unknown_aid_item', message: 'The linked aid item could not be found. Confirm whether this receipt is aid or another source of money.' }]);
      }
      const aid = ledger.aid.find((item) => item.id === update.aid_id);
      if (!Array.isArray(aid.restrictions) || !Array.isArray(source.restrictions) || stableJson([...aid.restrictions].sort()) !== stableJson([...source.restrictions].sort())) return updateResult('needs_clarification', ledger, [], [], [{ code: 'aid_restrictions', message: 'Confirm the aid restrictions and select a money source that preserves them.' }]);
      const duplicateAidReceipt = ledger.actual_events.some((event) => event.kind === 'receipt' && !event.reversed_by && event.aid_id === update.aid_id);
      if (duplicateAidReceipt) return updateResult('needs_clarification', ledger, [], [], [{ code: 'aid_receipt_already_recorded', message: 'A receipt is already linked to this aid item. Review it before adding another.' }]);
    }
    let commitment;
    if (kind === 'expense' && update.commitment_id) {
      commitment = ledger.expense_commitments.find((item) => item.id === update.commitment_id);
      if (!commitment) return updateResult('needs_clarification', ledger, [], [], [{ code: 'unknown_commitment', message: 'The linked expense commitment could not be found.' }]);
    }

    if (kind === 'expense') {
      if (!Array.isArray(source.restrictions) || (source.restrictions.length && !source.restrictions.includes(update.category.trim()))) return updateResult('needs_clarification', ledger, [], [], [{ code: 'expense_restrictions', message: 'Confirm that these funds can pay for this expense category.' }]);
      if (commitment && commitment.category !== update.category.trim()) return updateResult('needs_clarification', ledger, [], [], [{ code: 'commitment_category', message: 'The selected commitment has a different expense category.' }]);
      if (!commitment && update.unplanned !== true && ledger.expense_commitments.some((item) => item.category === update.category.trim())) return updateResult('needs_clarification', ledger, [], [], [{ code: 'commitment_match_required', message: 'Link this spending to its planned expense, or explicitly confirm it is additional unplanned spending.' }]);
    }
    const next = structuredClone(ledger);
    const nextSource = next.money_sources[sourceIndex];
    if (balanceEffect === 'adjust_source') {
      const balanceDelta = kind === 'expense' ? -amount : amount;
      const nextBalance = nextSource.balance_cents + balanceDelta;
      if (!validCents(nextBalance)) return updateResult('needs_clarification', ledger, [], [], [{ code: 'balance_reconciliation_needed', message: 'This event does not reconcile with the selected source balance. Confirm the balance or choose another source.' }]);
      nextSource.balance_cents = nextBalance;
    }

    const actualEvent = {
      id: eventId,
      request_fingerprint: stableJson(update),
      kind,
      amount_cents: amount,
      effective_date: effectiveDate,
      money_source_id: sourceId,
      balance_effect: balanceEffect,
      ...(kind === 'expense' ? { category: update.category.trim() } : {}),
      ...(update.commitment_id ? { commitment_id: update.commitment_id } : {}),
      ...(update.aid_id ? { aid_id: update.aid_id } : {})
    };
    next.actual_events.push(actualEvent);
    nextSource.reflected_event_ids = [...new Set([...(nextSource.reflected_event_ids || []), eventId])];
    if (kind === 'receipt' && update.aid_id) {
      const aid = next.aid.find((item) => item.id === update.aid_id);
      actualEvent.aid_previous_stage = aid.stage;
      aid.stage = 'received';
      aid.actual_receipt_id = eventId;
    }

    const notes = [];
    if (kind === 'expense' && commitment) {
      commitment = next.expense_commitments.find((item) => item.id === update.commitment_id);
      if (!commitment.fulfilled_by_date || typeof commitment.fulfilled_by_date !== 'object' || Array.isArray(commitment.fulfilled_by_date)) commitment.fulfilled_by_date = {};
      commitment.fulfilled_by_date[effectiveDate] = (commitment.fulfilled_by_date[effectiveDate] || 0) + amount;
      notes.push(`Matched the actual expense to commitment ${commitment.id}; the forecast will show only the remaining amount for that date.`);
    } else if (kind === 'expense') {
      notes.push('No forecast commitment was linked. Review the expense schedule to make sure this expense is not still counted there.');
    }
    if (balanceEffect === 'already_reflected') notes.push('The selected balance already includes this event, so it was not adjusted again.');
    return updateResult('applied', next, [eventId, sourceId, ...(commitment ? [commitment.id] : [])], notes);
  }

  function dueOn(item, date, day) {
    if (item.date) return item.date === date;
    if (item.start_date) return item.start_date <= date && item.end_date >= date;
    if (item.day) return item.day === day;
    return item.start_day <= day && item.end_day >= day;
  }

  function forecast(ledger, startDate, scenarioId = 'baseline', actionCosts = []) {
    if (!ledger || !Array.isArray(ledger.money_sources) || !Array.isArray(ledger.expense_commitments)) {
      throw new TypeError('A ledger with money_sources and expense_commitments is required.');
    }
    if (!validDate(startDate)) throw new TypeError('startDate must be a valid YYYY-MM-DD date.');
    const scenario = typeof scenarioId === 'object' && scenarioId ? scenarioId : scenarios.find((item) => item.id === scenarioId);
    if (!scenario) throw new RangeError(`Unknown finance scenario: ${scenarioId}`);
    if (!Array.isArray(actionCosts)) throw new TypeError('actionCosts must be an array.');
    const warnings = [];
    let unknownOpening = false;
    const accessibleSources = ledger.money_sources.filter((source) => source.accessible === true);
    accessibleSources.filter((source) => source.currency !== 'USD').forEach((source) => warnings.push(`Accessible balance for ${source.id || 'a money source'} uses ${source.currency || 'an unknown currency'} and is excluded from this USD forecast.`));
    const restrictedSources = accessibleSources.filter((source) => source.currency === 'USD' && Array.isArray(source.restrictions) && source.restrictions.length > 0).map((source) => ({ ...source }));
    accessibleSources.filter((source) => !Array.isArray(source.restrictions)).forEach((source) => warnings.push(`Restrictions are unknown for ${source.id}; these funds remain separate.`));
    const unrestrictedUsdSources = accessibleSources.filter((source) => source.currency === 'USD' && Array.isArray(source.restrictions) && source.restrictions.length === 0).map((source) => ({ ...source }));
    accessibleSources.forEach((source) => {
      if (!validDate(source.as_of) || source.as_of < startDate) warnings.push(`Balance ${source.id} needs confirmation as of ${startDate}; its last snapshot is ${source.as_of || 'unknown'}.`);
      if (validDate(source.as_of) && source.as_of > startDate) warnings.push(`Balance ${source.id} is dated after the forecast start; confirm a matching opening balance.`);
    });
    const usableOn = (source, date) => (!source.available_on || source.available_on <= date) && (!source.expires_on || source.expires_on >= date);
    restrictedSources.forEach((source) => {
      if (!validCents(source.balance_cents) || source.restrictions.some((category) => typeof category !== 'string')) {
        warnings.push(`Restricted balance or permitted uses are unknown for ${source.id}.`);
        source.balance_cents = 0;
        source.restrictions = [];
      }
    });
    const support = [...(ledger.support || []).filter((item) => item.state === 'confirmed'), ...scenario.support].map((item, index) => {
      const remaining = item.amount_cents === undefined ? Infinity : item.amount_cents - (item.consumed_cents || 0);
      if (item.amount_cents !== undefined && !validCents(item.amount_cents)) throw new TypeError('Support amount must be non-negative integer cents.');
      return { ...item, id: item.id || `scenario_support_${index}`, remaining: Math.max(0, remaining) };
    }).sort((a, b) => a.id.localeCompare(b.id));
    const openingCents = unrestrictedUsdSources
      .reduce((total, source) => {
        if (!validCents(source.balance_cents)) {
          unknownOpening = true;
          warnings.push(`Unknown accessible balance for ${source.id || 'a money source'}; this forecast is incomplete.`);
          return total;
        }
        return total + (usableOn(source, startDate) ? source.balance_cents : 0);
      }, 0);
    let balanceCents = openingCents;
    const cashPools = unrestrictedUsdSources.filter((source) => usableOn(source, startDate) && validCents(source.balance_cents));
    const spendCash = (amount) => {
      cashPools.sort((a, b) => (a.expires_on || '9999-12-31').localeCompare(b.expires_on || '9999-12-31') || a.id.localeCompare(b.id));
      for (const pool of cashPools) {
        const paid = Math.min(pool.balance_cents, amount);
        pool.balance_cents -= paid;
        amount -= paid;
        if (!amount) break;
      }
    };
    const addCash = (amount, pool) => {
      const previousGap = Math.max(0, -balanceCents);
      balanceCents += amount;
      cashPools.push(pool);
      spendCash(previousGap);
    };
    let firstGap = null;
    const days = [];

    for (let day = 1; day <= DAY_COUNT; day += 1) {
      const date = dateAt(startDate, day - 1);
      let expiredCents = 0;
      for (const pool of cashPools) {
        if (pool.expires_on && pool.expires_on < date) {
          expiredCents += pool.balance_cents;
          balanceCents -= pool.balance_cents;
          pool.balance_cents = 0;
        }
      }
      let releasedCents = 0;
      if (day > 1) for (const source of unrestrictedUsdSources) {
        if (source.available_on === date && usableOn(source, date) && validCents(source.balance_cents)) {
          releasedCents += source.balance_cents;
          addCash(source.balance_cents, source);
        }
      }
      const receiptsToday = scenario.receipts.filter((receipt) => receipt.date ? receipt.date === date : receipt.day === day);
      const earlyCents = receiptsToday.filter((receipt) => receipt.timing !== 'after_expenses').reduce((total, receipt) => total + receipt.amount_cents, 0);
      const lateCents = receiptsToday.filter((receipt) => receipt.timing === 'after_expenses').reduce((total, receipt) => total + receipt.amount_cents, 0);
      const receiptsCents = earlyCents + lateCents;
      if (earlyCents) addCash(earlyCents, { id: `receipt_${day}_early`, balance_cents: earlyCents });
      const commitments = [...ledger.expense_commitments, ...actionCosts].filter((item) => dueOn(item, date, day)).sort((a, b) =>
        Number(b.essential !== false) - Number(a.essential !== false) || (a.priority ?? 100) - (b.priority ?? 100) || String(a.id).localeCompare(String(b.id)));
      let dueCents = 0;
      let supportCents = 0;
      let restrictedCents = 0;
      let unmetCents = 0;
      const affectedCommitmentIds = [];
      const unmetCommitmentIds = [];
      for (const expense of commitments) {
        if (expense.amount_cents === null || expense.amount_cents === undefined) {
          warnings.push(`Unknown cost for ${expense.id || expense.action_id || 'an action'} on ${date}; this forecast is incomplete.`);
          continue;
        }
        if (!validCents(expense.amount_cents)) throw new TypeError(`Commitment ${expense.id || ''} must have a non-negative integer amount in cents or null.`);
        let remainingCents = Math.max(0, expense.amount_cents - (expense.fulfilled_by_date?.[date] || 0));
        for (const coverage of support) {
          if (!dueOn(coverage, date, day) || !(coverage.categories?.includes(expense.category) || coverage.commitment_ids?.includes(expense.id))) continue;
          const covered = Math.min(remainingCents, coverage.remaining);
          remainingCents -= covered;
          coverage.remaining -= covered;
          supportCents += covered;
        }
        for (const source of restrictedSources) {
          if (!source.restrictions.includes(expense.category) || (source.expires_on && date > source.expires_on) || (source.available_on && date < source.available_on)) continue;
          const covered = Math.min(remainingCents, source.balance_cents);
          remainingCents -= covered;
          source.balance_cents -= covered;
          restrictedCents += covered;
        }
        if (remainingCents) {
          dueCents += remainingCents;
          affectedCommitmentIds.push(expense.id);
          const gap = Math.max(0, remainingCents - Math.max(0, balanceCents));
          if (gap && expense.essential !== false) {
            unmetCents += gap;
            unmetCommitmentIds.push(expense.id);
          }
          spendCash(remainingCents);
          balanceCents -= remainingCents;
        }
      }
      if (!firstGap && unmetCents > 0) firstGap = { day, date, amount_cents: unmetCents, affected_commitment_ids: unmetCommitmentIds };
      if (lateCents) addCash(lateCents, { id: `receipt_${day}_late`, balance_cents: lateCents });
      days.push({ day, date, released_cents: releasedCents, expired_cents: expiredCents, receipts_cents: receiptsCents, support_cents: supportCents, restricted_cents: restrictedCents, expenses_cents: dueCents, unmet_cents: unmetCents, projected_cents: balanceCents, affected_commitment_ids: affectedCommitmentIds });
    }
    const uniqueWarnings = [...new Set(warnings)];
    const complete = uniqueWarnings.length === 0;
    const projectedDays = complete ? days : days.map((day) => ({
      ...day,
      known_projected_cents: day.projected_cents,
      known_unmet_cents: day.unmet_cents,
      projected_cents: null,
      unmet_cents: null
    }));
    return {
      scenario_id: scenario.id,
      label: scenario.label,
      description: scenario.description,
      start_date: startDate,
      end_date: dateAt(startDate, DAY_COUNT - 1),
      input_case_version: null,
      opening_cents: unknownOpening ? null : openingCents,
      first_gap: complete ? firstGap : null,
      partial_first_gap: complete ? null : firstGap,
      ending_projected_cents: complete ? balanceCents : null,
      ending_projected_position_cents: complete ? balanceCents : null,
      assumptions: ['Receipts default to before expenses; explicit after_expenses timing preserves earlier gaps. Dated availability and expiry are respected.', 'Actual expenses linked to commitments reduce only the matching date.', 'Confirmed support, then compatible restricted funds, then cash; essential expenses, priority, and stable IDs determine allocation order.'],
      warnings: uniqueWarnings,
      days: projectedDays
    };
  }

  function compare(ledger, startDate) {
    return scenarios.map((scenario) => forecast(ledger, startDate, scenario.id));
  }

  function forecastFinances(input) {
    if (!input || typeof input !== 'object') throw new TypeError('Forecast input is required.');
    const { ledger, start_date: startDate, case_time_zone: timeZone, input_case_version: inputVersion, scenarios: requestedScenarios = [], action_alternatives: alternatives = [] } = input;
    if (!validDate(startDate)) throw new TypeError('start_date must be a valid YYYY-MM-DD date.');
    if (typeof timeZone !== 'string' || !timeZone) throw new TypeError('case_time_zone is required.');
    try { new Intl.DateTimeFormat('en-US', { timeZone }).format(new Date(`${startDate}T12:00:00Z`)); }
    catch { throw new TypeError('case_time_zone must be a valid IANA time zone.'); }
    if (inputVersion !== undefined && (!Number.isSafeInteger(inputVersion) || inputVersion < 1)) throw new TypeError('input_case_version must be a positive integer.');
    if (!Array.isArray(requestedScenarios) || requestedScenarios.length > 3) throw new TypeError('Provide no more than three hypothetical scenarios.');
    if (!Array.isArray(alternatives) || alternatives.length > 3) throw new TypeError('Provide no more than three action alternatives.');
    const scenarioIds = new Set(['baseline']);
    requestedScenarios.forEach((scenario) => {
      if (!scenario || typeof scenario.id !== 'string' || !scenario.id || scenarioIds.has(scenario.id) || !Array.isArray(scenario.support) || !Array.isArray(scenario.receipts)) throw new TypeError('Each hypothetical scenario needs a unique ID, support array, and receipts array.');
      scenario.support.forEach((item) => {
        if (!item || !Array.isArray(item.categories) || item.categories.some((category) => typeof category !== 'string') || !Number.isInteger(item.start_day) || !Number.isInteger(item.end_day) || item.start_day < 1 || item.end_day > DAY_COUNT || item.end_day < item.start_day) throw new TypeError(`Scenario ${scenario.id} contains invalid support coverage.`);
      });
      scenario.receipts.forEach((receipt) => {
        if (!receipt || !validCents(receipt.amount_cents) || !(validDate(receipt.date) || (Number.isInteger(receipt.day) && receipt.day >= 1 && receipt.day <= DAY_COUNT)) || (receipt.timing !== undefined && !['before_expenses', 'after_expenses'].includes(receipt.timing))) throw new TypeError(`Scenario ${scenario.id} contains an invalid hypothetical receipt.`);
      });
      scenarioIds.add(scenario.id);
    });
    alternatives.forEach((alternative) => {
      if (!alternative || typeof alternative.id !== 'string' || !alternative.id || !Array.isArray(alternative.costs)) throw new TypeError('Each action alternative needs an ID and a costs array.');
      alternative.costs.forEach((cost) => {
        if (!cost || !validDate(cost.date) || !(cost.amount_cents === null || validCents(cost.amount_cents))) throw new TypeError('Each action cost needs a valid date and a non-negative integer amount in cents or null.');
      });
    });
    const baseline = forecast(ledger, startDate, 'baseline');
    const scenarioResults = requestedScenarios.map((scenario) => forecast(ledger, startDate, scenario));
    const actionComparisons = alternatives.map((alternative) => ({
      alternative_id: alternative.id,
      result: { ...forecast(ledger, startDate, 'baseline', alternative.costs), input_case_version: inputVersion ?? null }
    }));
    return {
      input_case_version: inputVersion ?? null,
      start_date: startDate,
      end_date: dateAt(startDate, DAY_COUNT - 1),
      case_time_zone: timeZone,
      baseline: { ...baseline, input_case_version: inputVersion ?? null },
      scenarios: scenarioResults.map((result) => ({ ...result, input_case_version: inputVersion ?? null })),
      action_comparisons: actionComparisons,
      assumptions: baseline.assumptions,
      warnings: [...baseline.warnings]
    };
  }

  const api = Object.freeze({ DAY_COUNT, scenarios: Object.freeze(scenarios), applyFinancialUpdate, apply_financial_update: applyFinancialUpdate, forecast, forecastFinances, forecast_finances: forecastFinances, compare });
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.StillHereFinance = api;
})();
// Built by Raneem Mousa
