/* Synthetic P2 fixtures shaped from CaseSnapshot 0.1. */
(() => {
  const timestamp = '2026-10-10T15:00:00Z';
  const emptySnapshot = {
    contract_version: '0.1',
    case_id: 'case_demo_p2',
    case_version: 1,
    updated_at: timestamp,
    time_zone: 'America/Chicago',
    household_mode: 'synthetic',
    facts: {},
    needs: [],
    evidence: [],
    resources: { state: 'not_requested', items: [], notices: [] },
    plan: { state: 'not_requested', version: 0, actions: [], blockers: [], questions: [] },
    applications: [],
    finance: {
      state: 'not_calculated',
      ledger: {
        money_sources: [{ id: 'cash_demo_001', type: 'cash', balance_cents: 30000, accessible: true, as_of: '2026-10-10', currency: 'USD', restrictions: [] }],
        actual_events: [],
        expense_commitments: [
          { id: 'food_daily', category: 'food', amount_cents: 2000, start_day: 1, end_day: 14, essential: true },
          { id: 'lodging_daily', category: 'lodging', amount_cents: 4000, start_day: 1, end_day: 14, essential: true },
          { id: 'transport_daily', category: 'transport', amount_cents: 500, start_day: 1, end_day: 14, essential: true },
          { id: 'recovery_once', category: 'recovery', amount_cents: 3000, day: 1, essential: true }
        ],
        aid: [],
        support: []
      },
      scenarios: [],
      baseline: null,
      input_case_version: 1,
      computed_at: null
    },
    check_in: { enrolled: false, status: 'not_enrolled', schedule: null, last_report: null, attempts: [] },
    shared_location: null,
    follow_ups: [],
    conversation: { turns: [] },
    components: [],
    sources: [],
    notices: [{ code: 'synthetic_demo', message: 'All case and financial values are demonstration data.' }]
  };

  window.StillHereFixtures = Object.freeze({ emptySnapshot });
})();
