/* Browser-only adapter. It mirrors the implemented P1 0.1 intake/correction boundary. */
(() => {
  const STORE = 'stillhere.p2.mock-case.v1';
  const clone = (value) => structuredClone(value);
  const timestamp = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');

  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE));
      if (saved?.case_snapshot?.contract_version === '0.1' && saved.events) return saved;
    } catch { /* Restore the synthetic fixture when local storage is unavailable or malformed. */ }
    return { case_snapshot: clone(window.StillHereFixtures.emptySnapshot), events: {} };
  }

  let data = load();
  function persist() {
    try { localStorage.setItem(STORE, JSON.stringify(data)); } catch { /* The adapter still works in memory for this tab. */ }
  }
  function readCase() { return clone(data.case_snapshot); }
  function result(eventId, status, issues = []) {
    return {
      contract_version: '0.1', event_id: eventId, status,
      received_at: timestamp(),
      applied_case_version: status === 'applied' ? data.case_snapshot.case_version : status === 'already_applied' ? data.events[eventId]?.case_version ?? null : null,
      case_snapshot: readCase(), issues
    };
  }
  function issue(code, message, retryable = false) { return { code, message, retryable }; }
  function stableJson(value) {
    if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
    if (value && typeof value === 'object') return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
    return JSON.stringify(value);
  }
  function fingerprint(command) {
    const { contract_version, case_id, event_id, occurred_at, channel, type, payload } = command;
    return stableJson({ contract_version, case_id, event_id, occurred_at, channel, type, payload });
  }

  function isInstant(value) {
    return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value));
  }

  function intakeIssue(payload) {
    const enums = {
      help_urgency: ['urgent_safety', 'essentials_today', 'recovery_steps', 'unsure', null],
      crisis_type: ['flood', 'storm_hurricane', 'wildfire', 'earthquake', 'other', 'unsure', null],
      needs: ['shelter', 'food_water', 'health_support', 'transport', 'lost_documents', 'aid_applications', 'managing_money', 'unsure'],
      household_group: ['just_me', 'children_with_me', 'other_adults_with_me', 'helping_someone_else']
    };
    for (const [key, value] of Object.entries(payload)) {
      if (key === 'current_location') {
        if (value === null) continue;
        if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some((field) => !['place', 'postal_code'].includes(field))) return `Invalid current_location.`;
        if (typeof value.place !== 'string' || !value.place.trim()) {
          if (typeof value.postal_code !== 'string' || !/^\d{5}(-\d{4})?$/.test(value.postal_code)) return 'Enter a place or valid ZIP code.';
        }
        if (value.postal_code !== undefined && !/^\d{5}(-\d{4})?$/.test(value.postal_code)) return 'Enter a valid ZIP code.';
        continue;
      }
      if (!Object.hasOwn(enums, key)) return `Unsupported intake field: ${key}.`;
      if (key === 'needs' || key === 'household_group') {
        if (value === null) continue;
        if (!Array.isArray(value) || value.length > (key === 'needs' ? 8 : 4) || new Set(value).size !== value.length || value.some((item) => !enums[key].includes(item))) return `Invalid ${key} selection.`;
        const exclusive = key === 'needs' ? 'unsure' : 'just_me';
        if (value.includes(exclusive) && value.length > 1) return `${exclusive} must be selected alone.`;
        continue;
      }
      if (!enums[key].includes(value)) return `Invalid ${key} value.`;
    }
    return null;
  }

  function applyFact(snapshot, key, value, observedAt) {
    snapshot.facts[key] = {
      value: clone(value), state: value === null ? 'unknown' : 'user_reported',
      observed_at: observedAt, source_ids: []
    };
    if (snapshot.plan.state !== 'not_requested') {
      snapshot.plan.state = 'pending';
      snapshot.plan.pending_input_case_version = snapshot.case_version + 1;
    }
    if (snapshot.finance.state !== 'not_calculated') {
      snapshot.finance.state = 'pending';
      snapshot.finance.pending_input_case_version = snapshot.case_version + 1;
    }
  }

  function submit(command) {
    if (!command || command.contract_version !== '0.1' || typeof command.event_id !== 'string' || !command.event_id || typeof command.case_id !== 'string' || !command.case_id || !Number.isInteger(command.expected_case_version) || command.expected_case_version < 1 || !isInstant(command.occurred_at) || !command.payload || typeof command.payload !== 'object' || Array.isArray(command.payload)) {
      return result(command?.event_id || '', 'rejected', [issue('invalid_command', 'A versioned command, case ID, and event ID are required.')]);
    }
    if (command.case_id !== data.case_snapshot.case_id) {
      return result(command.event_id, 'rejected', [issue('case_not_found', 'This demo case is not available.')]);
    }
    if (!['chat', 'dashboard', 'text_simulator'].includes(command.channel)) {
      return result(command.event_id, 'rejected', [issue('forbidden_channel', 'This browser demo cannot submit operator or system commands.')]);
    }
    if (!['intake.submit', 'fact.correct'].includes(command.type)) {
      return result(command.event_id, 'rejected', [issue('unsupported_command', 'The P1 service currently supports intake.submit and fact.correct only.')]);
    }
    if (data.events[command.event_id]) {
      return data.events[command.event_id].fingerprint === fingerprint(command)
        ? result(command.event_id, 'already_applied')
        : result(command.event_id, 'rejected', [issue('event_id_reused', 'This event ID was already used for a different change.')]);
    }
    if (command.expected_case_version !== data.case_snapshot.case_version) {
      return result(command.event_id, 'conflict', [issue('version_conflict', 'The demo case changed. Reload it before trying again.', true)]);
    }
    if (command.type === 'fact.correct') {
      const payload = command.payload || {};
      if (Object.keys(payload).some((key) => !['fact_key', 'value', 'observed_at'].includes(key)) || !/^[a-z][a-z0-9_]{0,63}$/.test(payload.fact_key || '') || !Object.hasOwn(payload, 'value') || !isInstant(payload.observed_at)) {
        return result(command.event_id, 'rejected', [issue('invalid_fact', 'The fact correction is missing a valid key, value, or observation time.')]);
      }
      applyFact(data.case_snapshot, payload.fact_key, payload.value, payload.observed_at);
    } else if (command.type === 'intake.submit') {
      const payload = command.payload || {};
      const invalid = intakeIssue(payload);
      if (invalid) return result(command.event_id, 'rejected', [issue('invalid_intake', invalid)]);
      for (const key of ['help_urgency', 'crisis_type', 'household_group', 'current_location']) {
        if (Object.hasOwn(payload, key)) applyFact(data.case_snapshot, key, payload[key], command.occurred_at || timestamp());
      }
      if (Object.hasOwn(payload, 'needs')) {
        applyFact(data.case_snapshot, 'requested_needs', payload.needs, command.occurred_at || timestamp());
        const kinds = Array.isArray(payload.needs) ? payload.needs.filter((kind) => kind !== 'unsure') : [];
        const urgency = ['urgent_safety', 'essentials_today', 'recovery_steps'].includes(payload.help_urgency) ? payload.help_urgency : 'unknown';
        for (const kind of kinds) {
          if (!['shelter', 'food_water', 'health_support', 'transport', 'lost_documents', 'aid_applications', 'managing_money'].includes(kind)) continue;
          const existing = data.case_snapshot.needs.find((need) => need.kind === kind);
          if (existing) existing.reported_urgency = urgency;
          else data.case_snapshot.needs.push({ id: `need_${kind}_demo`, kind, reported_urgency: urgency, state: 'unknown', source_ids: [], fact_keys: ['requested_needs'] });
        }
      }
    } else {
      return result(command.event_id, 'rejected', [issue('unsupported_command', 'The P1 service currently supports intake.submit and fact.correct only.')]);
    }
    data.case_snapshot.case_version += 1;
    data.case_snapshot.updated_at = timestamp();
    data.events[command.event_id] = { type: command.type, case_version: data.case_snapshot.case_version, fingerprint: fingerprint(command) };
    persist();
    return result(command.event_id, 'applied');
  }

  function reset() {
    data = { case_snapshot: clone(window.StillHereFixtures.emptySnapshot), events: {} };
    persist();
    return readCase();
  }

  window.StillHereMockService = Object.freeze({ readCase, submit, reset });
})();
