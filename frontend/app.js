(() => {
  const STORE = 'stillhere.simple-demo.v1';
  let storageAvailable = true;
  const defaultState = {
    city: 'New Orleans, Louisiana',
    locationShared: false,
    locationPromptSeen: false,
    active: true,
    incident: 'hurricane',
    affected: true,
    need: 'Somewhere safe to stay',
    selectedNeeds: ['Somewhere safe to stay'],
    selectedObstacles: [],
    stage: 'safety',
    chatMode: 'recovery',
    generalActive: false,
    generalMessages: [],
    financeActive: false,
    financeStage: 'topic',
    financeTopic: 'other',
    financeTurns: 0,
    financeMessages: [],
    messages: [
      { role: 'user', text: 'I need somewhere safe to stay tonight.' },
      { role: 'assistant', text: 'I can help. Are you in immediate danger right now?' }
    ]
  };

  function loadState() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE));
      if (!saved || typeof saved !== 'object') return structuredClone(defaultState);
      const restored = { ...defaultState, ...saved };
      if (!Array.isArray(saved.selectedNeeds)) restored.selectedNeeds = saved.need ? [saved.need] : [];
      if (!Array.isArray(saved.selectedObstacles)) restored.selectedObstacles = [];
      if (!Array.isArray(saved.generalMessages)) restored.generalMessages = [];
      if (!Array.isArray(saved.financeMessages)) restored.financeMessages = [];
      return restored;
    } catch {
      storageAvailable = false;
      return structuredClone(defaultState);
    }
  }

  let state = loadState();
  let toastTimer;
  let selectedFinanceScenario = 'baseline';
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  function save() {
    try {
      localStorage.setItem(STORE, JSON.stringify(state));
      storageAvailable = true;
    } catch {
      storageAvailable = false;
    }
    updateSaveStatus();
    return storageAvailable;
  }

  function updateSaveStatus() {
    const label = $('#connection-label');
    const retry = $('#retry-save');
    if (!label || !retry) return;
    label.textContent = storageAvailable ? 'Saved on this device' : 'Not saved on this device';
    retry.classList.toggle('is-hidden', storageAvailable);
  }

  function showToast(message) {
    const toast = $('#toast');
    toast.textContent = message;
    toast.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('is-visible'), 2400);
  }

  function showLocationPrompt() {
    $('#prompt-city').textContent = state.city || 'No city saved';
    $('#location-prompt').classList.remove('is-hidden');
    $('#share-saved-city').focus({ preventScroll: true });
  }

  function hideLocationPrompt() {
    $('#location-prompt').classList.add('is-hidden');
  }

  function shareSavedCity() {
    state.locationShared = true;
    state.locationPromptSeen = true;
    save();
    submitMockCommand('intake.submit', { current_location: { place: state.city } });
    hideLocationPrompt();
    updateHome();
    showToast('Your city is saved for local demo notices.');
  }

  function isLouisianaDemoCity(city = state.city) {
    const value = city.toLowerCase();
    return value.includes('louisiana') || ['new orleans', 'baton rouge', 'shreveport', 'lafayette', 'lake charles', 'monroe', 'houma', 'alexandria'].some((name) => value.includes(name));
  }

  function setScreen(name) {
    $$('[data-screen]').forEach((screen) => screen.classList.toggle('is-active', screen.dataset.screen === name));
    $('#site-menu').classList.add('is-hidden');
    $('#menu-toggle').setAttribute('aria-expanded', 'false');
    window.scrollTo({ top: 0 });
    if (name === 'home') history.replaceState(null, '', '#home');
    else history.replaceState(null, '', `#${name}`);
    if (name === 'chat') renderChat();
    if (name === 'finance') renderFinance();
    if (name === 'location') {
      $('#city-input').value = state.city;
      $('#stop-sharing-city').classList.toggle('is-hidden', !state.locationShared);
    }
  }

  function updateHome() {
    $('#city-label').textContent = state.city || 'Add your city';
    $('#prompt-city').textContent = state.city || 'No city saved';
    const storm = $('.storm-card');
    if (!state.locationShared) {
      storm.innerHTML = `
        <div class="storm-topline"><span class="storm-icon" aria-hidden="true">⌖</span><span class="storm-label">LOCAL NOTICES</span></div>
        <h2 id="storm-heading">Share your city to check nearby notices.</h2>
        <p>You can still open a recovery chat without sharing your location.</p>
        <div class="storm-actions"><button class="button button-primary" id="share-location-again">Choose whether to share <span aria-hidden="true">→</span></button></div>`;
    } else if (isLouisianaDemoCity()) {
      storm.innerHTML = `
        <div class="storm-topline"><span class="storm-icon" aria-hidden="true">✳</span><span class="storm-label">DEMO DISASTER NOTICE</span><span class="storm-place" id="storm-place">LOUISIANA · HURRICANE SCENARIO</span></div>
        <h2 id="storm-heading">A hurricane may be affecting your area.</h2>
        <p>Are you affected, or do you need help because of the storm?</p>
        <div class="storm-actions"><button class="button button-primary" id="affected-yes">Yes, I’m affected <span aria-hidden="true">→</span></button><button class="button button-secondary" id="affected-unsure">I’m not sure</button></div>
        <button class="quiet-link" id="affected-no">No, but I still need help</button>`;
    } else {
      storm.innerHTML = `
        <div class="storm-topline"><span class="storm-icon" aria-hidden="true">⌖</span><span class="storm-label">LOCAL DEMO NOTICES</span><span class="storm-place">NO MATCH</span></div>
        <h2>No matching demo disaster notice for your city.</h2>
        <p>You can still open a chat to find recovery help. This demo only includes a Louisiana hurricane scenario.</p>
        <div class="storm-actions"><button class="button button-primary" id="affected-no">Start a chat <span aria-hidden="true">→</span></button></div>`;
    }
    $('#continue-card').classList.toggle('is-hidden', !state.active);
    const needsSummary = currentNeeds() || 'Your needs';
    $('#resume-summary').textContent = state.stage === 'steps' ? `${needsSummary} · next steps are ready to review.` : `${needsSummary} · a few questions are still open.`;
    $('#finance-chat-start').textContent = state.financeActive ? 'Continue finance chat' : 'Chat about finances';
    $('#chat-context-label').textContent = `${state.incident === 'hurricane' && state.affected ? 'Hurricane help' : 'Recovery help'} · ${shortCity(state.city)}`;
  }

  function shortCity(city) {
    const [name, region] = city.split(',').map((part) => part.trim());
    return region ? `${name}, ${region === 'Louisiana' ? 'LA' : region}` : name;
  }

  let commandSequence = 0;
  function eventId() {
    commandSequence += 1;
    const randomPart = window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}_${commandSequence}`;
    return `p2_${randomPart}`;
  }

  function submitMockCommand(type, payload) {
    const snapshot = window.StillHereMockService.readCase();
    const result = window.StillHereMockService.submit({
      contract_version: '0.1',
      case_id: snapshot.case_id,
      event_id: eventId(),
      expected_case_version: snapshot.case_version,
      occurred_at: new Date().toISOString(),
      channel: 'chat',
      type,
      payload
    });
    if (!['applied', 'already_applied'].includes(result.status)) {
      showToast(result.issues?.[0]?.message || 'That answer could not be saved to the demo case.');
      return false;
    }
    return true;
  }

  function recoveryIntakeContext() {
    return {
      crisis_type: state.incident === 'hurricane' ? 'storm_hurricane' : 'other',
      ...(state.locationShared && state.city ? { current_location: { place: state.city } } : {})
    };
  }

  function syncRecoveryNeeds() {
    const kinds = new Set();
    const freeText = [];
    const mapping = {
      'Somewhere safe to stay': ['shelter'],
      'Food and water': ['food_water'],
      'Medicine or medical care': ['health_support'],
      Transportation: ['transport'],
      'Documents or money': ['lost_documents', 'managing_money']
    };
    (state.selectedNeeds || []).forEach((item) => {
      if (mapping[item]) mapping[item].forEach((kind) => kinds.add(kind));
      else if (item.startsWith('Something else: ')) freeText.push(item.slice('Something else: '.length));
    });
    const saved = submitMockCommand('intake.submit', { ...recoveryIntakeContext(), needs: [...kinds] });
    if (freeText.length) submitMockCommand('fact.correct', { fact_key: 'additional_needs', value: freeText, observed_at: new Date().toISOString() });
    return saved;
  }

  function syncRecoveryBarriers() {
    // Uses P1's flexible fact.correct envelope; it adds no new command type.
    const barriers = (state.selectedObstacles || []).includes('No obstacles right now') ? [] : (state.selectedObstacles || []);
    return submitMockCommand('fact.correct', { fact_key: 'access_barriers', value: barriers, observed_at: new Date().toISOString() });
  }

  function currentNeeds() {
    return (state.selectedNeeds || []).join(', ') || state.need || '';
  }

  function money(cents) {
    if (!Number.isSafeInteger(cents)) return 'Unknown';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(cents / 100);
  }

  function renderFinance() {
    const snapshot = window.StillHereMockService.readCase();
    const ledger = snapshot.finance.ledger;
    const results = window.StillHereFinance.compare(ledger, '2026-10-10');
    const selected = results.find((scenario) => scenario.scenario_id === selectedFinanceScenario) || results[0];
    const options = $('#finance-scenarios');
    options.replaceChildren();
    results.forEach((scenario) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'scenario-option';
      button.dataset.financeScenario = scenario.scenario_id;
      button.setAttribute('aria-pressed', String(scenario.scenario_id === selected.scenario_id));
      const title = document.createElement('strong');
      title.textContent = scenario.label;
      const result = document.createElement('span');
      result.textContent = scenario.warnings.length ? 'More information needed' : scenario.first_gap ? `First gap: Day ${scenario.first_gap.day} · ${money(scenario.first_gap.amount_cents)}` : `No gap · ${money(scenario.ending_projected_cents)} projected at Day 14`;
      button.append(title, result);
      options.append(button);
    });

    $('#finance-scenario-description').textContent = selected.description;
    $('#finance-first-gap').textContent = selected.first_gap ? `Day ${selected.first_gap.day} · ${money(selected.first_gap.amount_cents)}` : 'None in 14 days';
    $('#finance-gap-caption').textContent = selected.first_gap ? 'Example costs exceed available money that day' : 'Under this conditional example';
    $('#finance-gap-title').textContent = selected.first_gap ? `In this example, there’s a ${money(selected.first_gap.amount_cents)} shortfall on day ${selected.first_gap.day}.` : 'No listed expenses are uncovered in this 14-day example.';
    $('#finance-gap-detail').textContent = selected.first_gap ? 'This is the amount the example costs exceed the projected balance that day.' : `The projected amount after listed costs on day 14 is ${money(selected.ending_projected_cents)}.`;

    if (selected.warnings.length) {
      $('#finance-first-gap').textContent = 'Not yet known';
      $('#finance-gap-caption').textContent = 'Some financial details are missing';
      $('#finance-gap-title').textContent = 'This forecast is incomplete.';
      $('#finance-gap-detail').textContent = selected.warnings.join(' ');
    }
    const rows = $('#finance-forecast-rows');
    rows.replaceChildren();
    selected.days.forEach((day) => {
      const row = document.createElement('tr');
      [ `Day ${day.day} · ${day.date}`, day.receipts_cents ? money(day.receipts_cents) : '—', money(day.expenses_cents), money(day.projected_cents), day.unmet_cents === null ? 'Unknown' : day.unmet_cents ? money(day.unmet_cents) : '—' ].forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.append(cell);
      });
      rows.append(row);
    });
  }

  function activeMessages() {
    if (state.chatMode === 'finance') return state.financeMessages;
    if (state.chatMode === 'general') return state.generalMessages;
    return state.messages;
  }

  function addMessage(role, text) {
    activeMessages().push({ role, text });
    if (state.chatMode === 'finance') state.financeActive = true;
    else if (state.chatMode === 'general') state.generalActive = true;
    else state.active = true;
    save();
    renderMessages();
  }

  function addAssistant(text) { addMessage('assistant', text); }
  function addUser(text) { addMessage('user', text); }

  function messageNode(message) {
    const row = document.createElement('div');
    row.className = `message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`;
    const avatar = document.createElement('div');
    avatar.className = 'assistant-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.textContent = message.role === 'user' ? 'RH' : 's.';
    const body = document.createElement('div');
    body.className = 'message-body';
    const p = document.createElement('p');
    p.textContent = message.text;
    const time = document.createElement('small');
    time.innerHTML = message.role === 'user' ? 'You <span>·</span> just now' : 'StillHere <span>·</span> just now';
    body.append(p, time);
    row.append(avatar, body);
    return row;
  }

  function appendChoices(container, choices, className) {
    const group = document.createElement('div');
    group.className = className;
    group.setAttribute('aria-label', className.includes('quick') ? 'Choose what you need first' : 'Choose whether you are safe');
    choices.forEach((choice) => {
      const button = document.createElement('button');
      button.className = className.includes('quick') ? 'choice-card' : 'safety-choice';
      button.type = 'button';
      if (className.includes('quick')) button.dataset.need = choice.value;
      else button.dataset.answer = choice.value;
      const label = className.includes('quick') ? `<span class="choice-icon" aria-hidden="true">${choice.icon}</span><span></span><i aria-hidden="true">→</i>` : '<span></span>';
      button.innerHTML = label;
      if (className.includes('quick')) button.querySelector('span:nth-child(2)').textContent = choice.label;
      else button.querySelector('span').textContent = choice.label;
      group.append(button);
    });
    container.append(group);
  }

  function appendMultiChoices(container, choices, selected, type, label) {
    const hint = document.createElement('p');
    hint.className = 'selection-hint';
    hint.textContent = label;
    container.append(hint);
    const group = document.createElement('div');
    group.className = 'quick-options';
    group.setAttribute('aria-label', label);
    choices.forEach((choice) => {
      const button = document.createElement('button');
      button.className = 'choice-card';
      button.type = 'button';
      button.dataset[type] = choice.value;
      button.setAttribute('aria-pressed', String(selected.includes(choice.value)));
      const icon = document.createElement('span');
      icon.className = 'choice-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = choice.icon;
      const text = document.createElement('span');
      text.textContent = choice.label;
      const mark = document.createElement('i');
      mark.className = 'selection-mark';
      mark.setAttribute('aria-hidden', 'true');
      mark.textContent = selected.includes(choice.value) ? '✓' : '+';
      button.append(icon, text, mark);
      group.append(button);
    });
    container.append(group);
  }

  function appendStageAction(container, label) {
    const actions = document.createElement('div');
    actions.className = 'stage-actions';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button button-primary';
    button.id = 'continue-stage';
    button.textContent = label;
    actions.append(button);
    if (state.stage === 'need' || state.stage === 'obstacles') {
      const skip = document.createElement('button');
      skip.type = 'button';
      skip.className = 'quiet-link';
      skip.id = state.stage === 'need' ? 'skip-needs' : 'skip-obstacles';
      skip.textContent = 'Skip for now';
      actions.append(skip);
    }
    container.append(actions);
  }

  function appendFinanceTopics(container) {
    const group = document.createElement('div');
    group.className = 'safety-options finance-topic-options';
    group.setAttribute('aria-label', 'Choose a finance question');
    [
      ['available', 'Money I can use now'],
      ['costs', 'Bills or costs coming up'],
      ['aid', 'Aid or income I’m waiting for'],
      ['other', 'Something else']
    ].forEach(([value, label]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'safety-choice';
      button.dataset.financeTopic = value;
      button.textContent = label;
      group.append(button);
    });
    container.append(group);
  }

  function appendFinanceActions(container) {
    const actions = document.createElement('div');
    actions.className = 'finance-inline-actions';
    const budget = document.createElement('button');
    budget.type = 'button';
    budget.className = 'finance-inline-link';
    budget.dataset.pageLink = 'finance';
    budget.textContent = 'View the example budget →';
    actions.append(budget);
    if (state.active) {
      const back = document.createElement('button');
      back.type = 'button';
      back.className = 'quiet-link';
      back.id = 'return-to-recovery';
      back.textContent = 'Back to recovery questions';
      actions.append(back);
    }
    container.append(actions);
  }

  const needs = [
    { value: 'Somewhere safe to stay', label: 'Somewhere safe to stay', icon: '⌂' },
    { value: 'Food and water', label: 'Food and water', icon: '✳' },
    { value: 'Medicine or medical care', label: 'Medicine or medical care', icon: '＋' },
    { value: 'Transportation', label: 'Transportation', icon: '↗' },
    { value: 'Documents or money', label: 'Documents or money', icon: '▤' },
    { value: 'Something else', label: 'Something else', icon: '…' }
  ];

  const obstacles = [
    { value: 'Transportation', label: 'Getting there', icon: '↗' },
    { value: 'Childcare or caregiving', label: 'Childcare or caregiving', icon: '⌂' },
    { value: 'Cost or money', label: 'Cost or money', icon: '$' },
    { value: 'Medical or accessibility needs', label: 'Medical or accessibility needs', icon: '＋' },
    { value: 'Missing ID or Social Security documents', label: 'Missing ID or Social Security documents', icon: '▤' },
    { value: 'Phone or internet access', label: 'Phone or internet access', icon: '⌁' },
    { value: 'Language or information', label: 'Language or information', icon: '…' },
    { value: 'No obstacles right now', label: 'No obstacles right now', icon: '✓' }
  ];

  function appendNextSteps(container) {
    const card = document.createElement('div');
    card.className = 'next-steps';
    const eyebrow = document.createElement('p');
    eyebrow.className = 'eyebrow';
    eyebrow.textContent = 'A COUPLE OF NEXT STEPS';
    card.append(eyebrow);
    const firstNeed = (state.selectedNeeds || [state.need]).filter(Boolean)[0] || 'your most urgent need';
    const hasObstacle = state.selectedObstacles?.length && !state.selectedObstacles.includes('No obstacles right now');
    const steps = [
      ['1', firstNeed === 'Somewhere safe to stay' ? 'Let’s identify a safe place' : `Start with ${firstNeed.toLowerCase()}`, 'We’ll use your city and details you choose to share.'],
      ['2', hasObstacle ? `Plan around: ${state.selectedObstacles.join(', ')}` : 'Check what is available before you travel', hasObstacle ? 'We’ll keep these barriers in mind as we work through your needs.' : 'This demo has no live capacity or service information. Confirm with local officials.']
    ];
    steps.forEach(([number, title, description]) => {
      const row = document.createElement('div');
      row.className = 'next-step-row';
      row.innerHTML = `<span class="step-index">${number}</span><div><strong></strong><p></p></div>`;
      row.querySelector('strong').textContent = title;
      row.querySelector('p').textContent = description;
      card.append(row);
    });
    const source = document.createElement('p');
    source.className = 'demo-source';
    source.textContent = 'Example guidance · no resources have been contacted';
    card.append(source);
    const corrections = document.createElement('div');
    corrections.className = 'answer-corrections';
    [['need', 'Edit needs'], ['obstacles', 'Edit obstacles']].forEach(([stage, label]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'quiet-link';
      button.dataset.editStage = stage;
      button.textContent = label;
      corrections.append(button);
    });
    card.append(corrections);
    container.append(card);
  }

  function renderMessages() {
    const container = $('#messages');
    container.replaceChildren();
    activeMessages().forEach((message) => container.append(messageNode(message)));
    if (state.chatMode === 'finance') {
      if (state.financeStage === 'topic') appendFinanceTopics(container);
      appendFinanceActions(container);
    } else if (state.chatMode === 'general') {
      // General chat is free-form and keeps its own transcript.
    } else if (state.stage === 'urgent') {
      const actions = document.createElement('div');
      actions.className = 'stage-actions';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'button button-secondary';
      button.id = 'continue-after-urgent';
      button.textContent = 'I’m safe enough to continue';
      actions.append(button);
      container.append(actions);
    } else if (state.stage === 'need') {
      appendMultiChoices(container, needs, state.selectedNeeds || [], 'need', 'Choose all the kinds of help you need.');
      appendStageAction(container, 'Continue');
    } else if (state.stage === 'obstacles') {
      appendMultiChoices(container, obstacles, state.selectedObstacles || [], 'obstacle', 'Is anything making it harder to get help? Choose all that apply.');
      const privacyNote = document.createElement('p');
      privacyNote.className = 'selection-hint privacy-hint';
      privacyNote.textContent = 'You don’t need to type your Social Security number here.';
      container.append(privacyNote);
      appendStageAction(container, 'Continue');
    } else if (state.stage === 'safety') {
      appendChoices(container, [
        { value: 'safe_yes', label: 'Yes, I’m safe for now' },
        { value: 'safe_no', label: 'Yes, I’m in immediate danger' },
        { value: 'safe_unsure', label: 'I’m not sure' }
      ], 'safety-options');
    } else if (state.stage === 'steps') {
      appendNextSteps(container);
    }
    container.scrollTop = container.scrollHeight;
  }

  function renderChat() {
    updateHome();
    renderMessages();
    const financeMode = state.chatMode === 'finance';
    const generalMode = state.chatMode === 'general';
    $('#chat-thread-label').textContent = financeMode ? 'YOUR FINANCE CONVERSATION' : generalMode ? 'YOUR GENERAL CHAT' : 'YOUR RECOVERY CONVERSATION';
    $('#chat-context-label').textContent = financeMode ? `Finances · ${shortCity(state.city)}` : generalMode ? 'General support' : `${state.incident === 'hurricane' && state.affected ? 'Hurricane help' : 'Recovery help'} · ${shortCity(state.city)}`;
    $('#chat-step').textContent = financeMode ? '· FINANCE CONVERSATION' : generalMode ? '· GENERAL CONVERSATION' : state.stage === 'safety' ? '· CHECKING ON YOUR IMMEDIATE SAFETY' : state.stage === 'need' ? '· WHAT HELP DO YOU NEED?' : state.stage === 'obstacles' ? '· WHAT MIGHT GET IN THE WAY?' : state.stage === 'urgent' ? '· IMMEDIATE SAFETY' : '· YOUR NEXT STEPS';
    $('#new-chat').textContent = financeMode ? 'New finance chat' : generalMode ? 'New general chat' : 'Start over';
    $('#message-input').placeholder = financeMode ? 'Type a finance question…' : generalMode ? 'Type a message…' : state.stage === 'steps' ? 'Ask a question or tell us what changed…' : 'Type a message…';
    setTimeout(() => $('#message-input').focus({ preventScroll: true }), 0);
  }

  function startChat(mode) {
    state = {
      ...state,
      active: true,
      chatMode: 'recovery',
      incident: mode === 'affected' || mode === 'unsure' ? 'hurricane' : 'general',
      affected: mode === 'affected' ? true : mode === 'unsure' ? null : false,
      need: '',
      selectedNeeds: [],
      selectedObstacles: [],
      stage: 'safety',
      messages: [{ role: 'assistant', text: mode === 'unsure' ? 'That’s okay. Before anything else, are you in immediate danger right now?' : mode === 'affected' ? 'I’m sorry you’re dealing with this. Before anything else, are you in immediate danger right now?' : 'I’m here to help. Before we get started, are you in immediate danger right now?' }]
    };
    save();
    submitMockCommand('intake.submit', recoveryIntakeContext());
    updateHome();
    setScreen('chat');
  }

  function startFinanceChat() {
    if (state.chatMode === 'finance') {
      if (!state.financeMessages.length) {
        state.financeStage = 'topic';
        state.financeMessages.push({ role: 'assistant', text: 'Of course. What would you like to work through: money available now, upcoming costs, or support you’re waiting for? You can also type your question. Please don’t share bank, card, or Social Security numbers.' });
      }
      state.financeActive = true;
      save();
      setScreen('chat');
      return;
    }
    if (!state.financeMessages.length) {
      state.financeStage = 'topic';
      state.financeMessages.push({ role: 'assistant', text: 'Of course. What would you like to work through: money available now, upcoming costs, or support you’re waiting for? You can also type your question. Please don’t share bank, card, or Social Security numbers.' });
    }
    state.chatMode = 'finance';
    state.financeActive = true;
    save();
    setScreen('chat');
  }

  function startGeneralChat() {
    state.chatMode = 'general';
    if (!state.generalMessages.length) {
      state.generalMessages.push({ role: 'assistant', text: 'Hi, I’m here to help. What would you like to talk through? If this is about immediate danger, call 911 now.' });
    }
    state.generalActive = true;
    save();
    setScreen('chat');
  }

  function chooseFinanceTopic(topic) {
    const topics = {
      available: ['Money I can use now', 'Let’s start with money you can actually use today. An estimate is fine. Please don’t share account details.'],
      costs: ['Bills or costs coming up', 'What essential cost is coming up next, and when is it due? A rough amount is okay.'],
      aid: ['Aid or income I’m waiting for', 'Has that support arrived, or is it still pending? We’ll keep unreceived money separate from what’s available now.'],
      other: ['Something else', 'Tell me what you’re trying to figure out. Please leave out bank, card, and Social Security numbers.']
    };
    const [label, prompt] = topics[topic] || topics.other;
    state.chatMode = 'finance';
    addUser(label);
    state.financeTopic = topic;
    state.financeTurns = 0;
    state.financeStage = 'input';
    addAssistant(prompt);
    save();
    renderChat();
  }

  function returnToRecoveryChat() {
    state.chatMode = 'recovery';
    addAssistant('Back to your recovery chat. We can continue where you left off.');
    save();
    renderChat();
  }

  function financeFollowup(urgent) {
    if (urgent) return 'If you’re in immediate danger, call 911 now. I can help organize finances here, but this chat does not contact emergency services.';
    state.financeTurns = (state.financeTurns || 0) + 1;
    if (state.financeTurns > 1) return 'I’ve kept that with your finance notes. We can take it one piece at a time; the example budget on the Finances page is only a demonstration.';
    const replies = {
      available: 'Thanks. We’ll separate money you can use now from anything still expected. What essential cost comes due first?',
      costs: 'Got it. Which of those costs is due soonest, and is the amount exact or an estimate?',
      aid: 'Thanks. We won’t count pending support as available money. Do you know when it may arrive, or is the date unknown?',
      other: 'Thanks. What is the next piece you want to figure out? An estimate is fine; leave out account and identity numbers.'
    };
    return replies[state.financeTopic] || replies.other;
  }

  function chooseNeed(need) {
    const selected = new Set(state.selectedNeeds || []);
    if (selected.has(need)) selected.delete(need);
    else selected.add(need);
    state.selectedNeeds = [...selected];
    state.need = currentNeeds();
    save();
    syncRecoveryNeeds();
    renderChat();
  }

  function chooseObstacle(obstacle) {
    const selected = new Set(state.selectedObstacles || []);
    if (obstacle === 'No obstacles right now') {
      state.selectedObstacles = selected.has(obstacle) ? [] : [obstacle];
    } else {
      selected.delete('No obstacles right now');
      if (selected.has(obstacle)) selected.delete(obstacle);
      else selected.add(obstacle);
      state.selectedObstacles = [...selected];
    }
    save();
    syncRecoveryBarriers();
    renderChat();
  }

  function continueStage() {
    if (state.chatMode === 'finance') return;
    if (state.stage === 'need') {
      if (!state.selectedNeeds?.length) {
        showToast('Choose at least one kind of help, or type what you need.');
        return;
      }
      state.need = currentNeeds();
      state.stage = 'obstacles';
      addAssistant(`I’ll keep these needs in mind: ${state.need}. Is anything making it harder to get help?`);
    } else if (state.stage === 'obstacles') {
      state.stage = 'steps';
      addAssistant('Thanks. I’ll keep those barriers in mind as we work through the next steps.');
    }
    save();
    renderChat();
  }

  function chooseSafety(answer) {
    const labels = { safe_yes: 'Yes, I’m safe for now', safe_no: 'Yes, I’m in immediate danger', safe_unsure: 'I’m not sure' };
    addUser(labels[answer]);
    if (answer === 'safe_no') {
      state.stage = 'urgent';
      addAssistant('If you’re in immediate danger, call 911 now. I can also help you work through a next step here.');
    } else if (answer === 'safe_unsure') {
      state.stage = 'need';
      addAssistant('If you may be in immediate danger, call 911 and move away from immediate hazards if you can. If you’re safe enough to continue, choose all the kinds of help you need.');
    } else {
      state.stage = 'need';
      addAssistant('I’m glad you’re safe for now. What kinds of help do you need? Choose all that apply.');
    }
    submitMockCommand('intake.submit', { ...recoveryIntakeContext(), help_urgency: answer === 'safe_no' ? 'urgent_safety' : answer === 'safe_unsure' ? 'unsure' : 'recovery_steps' });
    save();
    renderChat();
  }

  function handleTextMessage(text) {
    const clean = text.trim();
    if (!clean) return;
    if (/(?:^|\D)\d{3}[- ]?\d{2}[- ]?\d{4}(?:$|\D)/.test(clean)) {
      showToast('For privacy, don’t enter an SSN here. Choose the missing-document option instead.');
      return;
    }
    addUser(clean);
    const urgent = /danger|unsafe|trapped|injur|hurt|emergency|can't breathe/i.test(clean);
    if (state.chatMode === 'finance') {
      if (state.financeStage === 'topic') {
        state.financeTopic = 'other';
        state.financeTurns = 0;
        state.financeStage = 'input';
      }
      addAssistant(financeFollowup(urgent));
    } else if (state.chatMode === 'general') {
      addAssistant(urgent ? 'If you’re in immediate danger, call 911 now. I can stay with you here to think through what to do next when it’s safe.' : 'Thanks for telling me. What feels like the most useful next thing to talk through? You can share as much or as little as you want.');
    } else if (state.stage === 'safety') {
      if (urgent || /\b(no|not safe|unsafe|in danger)\b/i.test(clean)) {
        state.stage = 'urgent';
        submitMockCommand('intake.submit', { ...recoveryIntakeContext(), help_urgency: 'urgent_safety' });
        addAssistant('If you may be in immediate danger, call 911 now. Move away from immediate hazards if you can. You can continue here when it is safe.');
      } else if (/\b(yes|safe|not sure|unsure|maybe)\b/i.test(clean)) {
        const uncertain = /not sure|unsure|maybe/i.test(clean);
        state.stage = 'need';
        submitMockCommand('intake.submit', { ...recoveryIntakeContext(), help_urgency: uncertain ? 'unsure' : 'recovery_steps' });
        addAssistant(uncertain ? 'If you may be in immediate danger, call 911. If you’re safe enough to continue, choose all the kinds of help you need.' : 'I’m glad you’re safe for now. What kinds of help do you need? Choose all that apply.');
      } else {
        addAssistant('Please choose one: safe for now, in immediate danger, or not sure.');
      }
    } else if (state.stage === 'urgent') {
      if (/\b(safe|continue|okay now)\b/i.test(clean)) {
        state.stage = 'need';
        addAssistant('Okay. Choose all the kinds of help you need.');
      } else {
        addAssistant('If you’re still in immediate danger, call 911 now. When it’s safe enough, you can continue here.');
      }
    } else if (urgent) {
      state.stage = 'urgent';
      addAssistant('If you’re in immediate danger, call 911 now. I can continue helping once it’s safe.');
    } else if (state.stage === 'need') {
      const typedNeed = `Something else: ${clean}`;
      if (!(state.selectedNeeds || []).includes(typedNeed)) state.selectedNeeds.push(typedNeed);
      state.need = currentNeeds();
      syncRecoveryNeeds();
      addAssistant('I’ve added that to your needs. Choose anything else that applies, then continue.');
    } else if (state.stage === 'obstacles') {
      if (!(state.selectedObstacles || []).includes(clean)) state.selectedObstacles.push(clean);
      syncRecoveryBarriers();
      addAssistant('I’ve added that as an obstacle. Choose anything else that applies, then continue.');
    } else {
      addAssistant('I’ve added that to our conversation. We can take it one step at a time. What would you like help with next?');
    }
    save();
    renderChat();
  }

  document.addEventListener('click', (event) => {
    if (!event.target.closest('.menu-wrap')) {
      $('#site-menu').classList.add('is-hidden');
      $('#menu-toggle').setAttribute('aria-expanded', 'false');
    }
    if (event.target.closest('#share-saved-city')) { shareSavedCity(); return; }
    if (event.target.closest('#choose-location-city')) { hideLocationPrompt(); setScreen('location'); return; }
    if (event.target.closest('#not-now')) {
      state.locationPromptSeen = true;
      save();
      hideLocationPrompt();
      updateHome();
      return;
    }
    if (event.target.closest('#share-location-again')) { showLocationPrompt(); return; }
    if (event.target.closest('#finance-chat-start')) { startFinanceChat(); return; }
    const financeScenario = event.target.closest('[data-finance-scenario]');
    if (financeScenario) {
      selectedFinanceScenario = financeScenario.dataset.financeScenario;
      renderFinance();
      return;
    }
    const financeTopic = event.target.closest('[data-finance-topic]');
    if (financeTopic) { chooseFinanceTopic(financeTopic.dataset.financeTopic); return; }
    if (event.target.closest('#return-to-recovery')) { returnToRecoveryChat(); return; }
    if (event.target.closest('#continue-after-urgent')) {
      state.stage = 'need';
      addAssistant('Okay. Choose all the kinds of help you need.');
      save();
      renderChat();
      return;
    }
    if (event.target.closest('#affected-yes')) { startChat('affected'); return; }
    if (event.target.closest('#affected-unsure')) { startChat('unsure'); return; }
    if (event.target.closest('#affected-no')) { startChat('general'); return; }
    const target = event.target.closest('[data-page-link]');
    if (target) {
      event.preventDefault();
      if (target.dataset.pageLink === 'chat' && target.dataset.chatMode === 'finance') { startFinanceChat(); return; }
      if (target.dataset.pageLink === 'chat' && target.dataset.chatMode === 'general') { startGeneralChat(); return; }
      if (target.dataset.pageLink === 'chat') state.chatMode = 'recovery';
      setScreen(target.dataset.pageLink);
    }
    const choice = event.target.closest('[data-need]');
    if (choice) chooseNeed(choice.dataset.need);
    const obstacle = event.target.closest('[data-obstacle]');
    if (obstacle) chooseObstacle(obstacle.dataset.obstacle);
    const safety = event.target.closest('[data-answer]');
    if (safety) chooseSafety(safety.dataset.answer);
    if (event.target.closest('#continue-stage')) continueStage();
    if (event.target.closest('#skip-needs')) {
      state.selectedNeeds = [];
      state.need = '';
      syncRecoveryNeeds();
      state.stage = 'obstacles';
      addAssistant('That’s okay. You can skip the needs list. Is anything making it harder to get help?');
      save();
      renderChat();
      return;
    }
    if (event.target.closest('#skip-obstacles')) {
      state.selectedObstacles = [];
      state.stage = 'steps';
      syncRecoveryBarriers();
      addAssistant('That’s okay. Here are a couple of next steps based on what you shared.');
      save();
      renderChat();
      return;
    }
    const editStage = event.target.closest('[data-edit-stage]');
    if (editStage) {
      state.stage = editStage.dataset.editStage;
      addAssistant(state.stage === 'need' ? 'You can change any of the needs you selected.' : 'You can change any obstacles you selected.');
      save();
      renderChat();
    }
  });

  $('#menu-toggle').addEventListener('click', () => {
    const menu = $('#site-menu');
    const opening = menu.classList.contains('is-hidden');
    menu.classList.toggle('is-hidden', !opening);
    $('#menu-toggle').setAttribute('aria-expanded', String(opening));
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      $('#site-menu').classList.add('is-hidden');
      $('#menu-toggle').setAttribute('aria-expanded', 'false');
    }
  });

  $('#continue-chat').addEventListener('click', () => { state.chatMode = 'recovery'; setScreen('chat'); });
  $('#back-home').addEventListener('click', () => setScreen('home'));
  $('#location-back').addEventListener('click', () => {
    setScreen('home');
    if (!state.locationPromptSeen && !state.locationShared) showLocationPrompt();
  });
  $('#open-location').addEventListener('click', () => setScreen('location'));
  $('#stop-sharing-city').addEventListener('click', () => {
    state.locationShared = false;
    state.locationPromptSeen = true;
    save();
    updateHome();
    setScreen('home');
    showToast('Your city is no longer used for local notices.');
  });

  $('#location-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const city = $('#city-input').value.trim();
    if (!city) { $('#city-input').focus(); return; }
    state.city = city;
    state.locationShared = true;
    state.locationPromptSeen = true;
    save();
    submitMockCommand('intake.submit', { current_location: { place: state.city } });
    updateHome();
    setScreen('home');
    hideLocationPrompt();
    showToast(isLouisianaDemoCity() ? 'City saved for local notices. Louisiana demo notice is available.' : 'City saved for local notices. No matching demo notice for this location.');
  });

  $('#message-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = $('#message-input');
    handleTextMessage(input.value);
    input.value = '';
    input.style.height = 'auto';
  });
  $('#retry-save').addEventListener('click', () => {
    showToast(save() ? 'Your conversation was saved on this device.' : 'Still unable to save. Keep this page open and try again.');
  });
  $('#message-input').addEventListener('input', (event) => {
    const input = event.currentTarget;
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 100)}px`;
  });

  $('#new-chat').addEventListener('click', () => {
    if (state.chatMode === 'finance') {
      state.financeActive = true;
      state.financeStage = 'topic';
      state.financeTopic = 'other';
      state.financeTurns = 0;
      state.financeMessages = [{ role: 'assistant', text: 'Let’s start a new finance conversation. What would you like to work through: money available now, upcoming costs, or support you’re waiting for? Please don’t share bank, card, or Social Security numbers.' }];
    } else if (state.chatMode === 'general') {
      state.generalActive = true;
      state.generalMessages = [{ role: 'assistant', text: 'Let’s start a new general chat. What would you like to talk through? If this is about immediate danger, call 911 now.' }];
    } else {
      state.active = true;
      state.incident = 'general';
      state.affected = false;
      state.need = '';
      state.selectedNeeds = [];
      state.selectedObstacles = [];
      state.stage = 'safety';
      state.messages = [{ role: 'assistant', text: 'Let’s start a new recovery conversation. Are you in immediate danger right now?' }];
    }
    save();
    renderChat();
  });

  const hash = window.location.hash.slice(1);
  updateSaveStatus();
  updateHome();
  if (hash === 'chat') setScreen('chat');
  else if (hash === 'location') setScreen('location');
  else setScreen('home');
  if (!state.locationPromptSeen && !state.locationShared) showLocationPrompt();
})();

// Built by Raneem Mousa
