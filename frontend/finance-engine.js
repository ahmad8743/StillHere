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

  function forecast(ledger, startDate, scenarioId = 'baseline') {
    if (!ledger || !Array.isArray(ledger.money_sources) || !Array.isArray(ledger.expense_commitments)) {
      throw new TypeError('A ledger with money_sources and expense_commitments is required.');
    }
    const scenario = scenarios.find((item) => item.id === scenarioId);
    if (!scenario) throw new RangeError(`Unknown finance scenario: ${scenarioId}`);
    const openingCents = ledger.money_sources
      .filter((source) => source.currency === 'USD' && source.accessible === true)
      .reduce((total, source) => total + source.balance_cents, 0);
    let balanceCents = openingCents;
    let firstGap = null;
    const days = [];

    for (let day = 1; day <= DAY_COUNT; day += 1) {
      const receiptsCents = scenario.receipts
        .filter((receipt) => receipt.day === day)
        .reduce((total, receipt) => total + receipt.amount_cents, 0);
      balanceCents += receiptsCents;
      const commitments = ledger.expense_commitments.filter((item) => {
        if (item.day) return item.day === day;
        return item.start_day <= day && item.end_day >= day;
      });
      let dueCents = 0;
      for (const expense of commitments) {
        const covered = scenario.support.some((item) => item.categories.includes(expense.category) && item.start_day <= day && item.end_day >= day);
        if (!covered) dueCents += expense.amount_cents;
      }
      const unmetCents = Math.max(0, dueCents - Math.max(0, balanceCents));
      if (!firstGap && unmetCents > 0) firstGap = { day, date: dateAt(startDate, day - 1), amount_cents: unmetCents };
      balanceCents -= dueCents;
      days.push({ day, date: dateAt(startDate, day - 1), receipts_cents: receiptsCents, expenses_cents: dueCents, unmet_cents: unmetCents, projected_cents: balanceCents });
    }
    return {
      scenario_id: scenario.id,
      label: scenario.label,
      description: scenario.description,
      opening_cents: openingCents,
      first_gap: firstGap,
      ending_projected_cents: balanceCents,
      days
    };
  }

  function compare(ledger, startDate) {
    return scenarios.map((scenario) => forecast(ledger, startDate, scenario.id));
  }

  window.StillHereFinance = Object.freeze({ DAY_COUNT, scenarios: Object.freeze(scenarios), forecast, compare });
})();
