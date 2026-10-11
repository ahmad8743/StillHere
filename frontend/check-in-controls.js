/* Optional check-in controls with one case-scoped, explicitly retried unsent change. */
(() => {
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const iso = (value) => new Date(value).toISOString().replace(/\.\d{3}Z$/, 'Z');
  const replies = { okay_for_now: 'I’m okay for now', need_help: 'I need help', check_later: 'Check in later' };
  const labels = {
    'check_in.enroll': 'Start a check-in', 'check_in.reply': 'Record your reply',
    'check_in.pause': 'Pause or stop check-ins', 'help.request': 'Record a help request',
    'location.share': 'Share a location for follow-up', 'location.clear': 'Remove the shared location'
  };

  function mount({ service, onChange = () => {} }) {
    const root = document.querySelector('#check-in-controls');
    const owner = service.readCase().case_id;
    const store = `stillhere.p2.check-in-pending.v1:${owner}`;
    let pending = null;
    let pendingSaved = true;
    let offlineDemo = false;
    let message = '';
    try {
      const saved = JSON.parse(localStorage.getItem(store));
      const command = saved?.command;
      if (command?.case_id === owner && command.contract_version === '0.1' && typeof command.event_id === 'string' && Number.isInteger(command.expected_case_version) && Number.isFinite(Date.parse(command.occurred_at)) && command.payload && typeof command.payload === 'object' && !Array.isArray(command.payload) && window.StillHereCheckInDemo.types.includes(command.type)) pending = saved;
      else if (saved) message = 'The saved unsent change could not be read. It has not been sent.';
    } catch { message = 'Device storage is unavailable. Unsent changes may not survive closing this page.'; }

    function persistPending() {
      try {
        if (pending) localStorage.setItem(store, JSON.stringify(pending));
        else localStorage.removeItem(store);
        pendingSaved = true;
      } catch { pendingSaved = false; }
    }
    function time(value, zone = service.readCase().time_zone) {
      if (!value || !Number.isFinite(Date.parse(value))) return 'Time unavailable';
      return new Intl.DateTimeFormat('en-US', { timeZone: zone, month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }).format(new Date(value));
    }
    function after(hours) { return iso(Date.parse(service.readCheckInTime()) + Number(hours) * 3600000); }
    function timeOptions() {
      return [1, 3, 6, 12, 24].map((hours) => `<option value="${hours}">In ${hours} hour${hours === 1 ? '' : 's'} · ${escape(time(after(hours)))}</option>`).join('');
    }
    function changed() {
      const focused = root.contains(document.activeElement) ? document.activeElement : null;
      const action = focused?.dataset.checkInAction;
      const id = focused?.id;
      render();
      onChange();
      if (focused) {
        const target = id ? document.getElementById(id) : action ? root.querySelector(`[data-check-in-action="${action}"]`) : null;
        const fallback = root.querySelector('.check-in-feedback:empty') ? root.querySelector('#check-in-state-title') : root.querySelector('.check-in-feedback');
        if (target && !target.disabled) target.focus({ preventScroll: true });
        else { fallback.tabIndex = -1; fallback.focus({ preventScroll: true }); }
      }
    }
    function send() {
      if (!pending) return;
      if (pending.command.case_id !== service.readCase().case_id) {
        message = 'This unsent change belongs to a different case. It was not sent.';
        changed();
        return;
      }
      if (offlineDemo || navigator.onLine === false) {
        pending.status = 'queued_local';
        pending.message = 'Waiting on this device. Nothing has been accepted by the demo case.';
        persistPending();
        changed();
        return;
      }
      let result;
      try { result = service.submit(pending.command); }
      catch { result = { status: 'unavailable', issues: [{ message: 'The demo service is unavailable. Your change is still unsent.' }] }; }
      if (['applied', 'already_applied'].includes(result.status)) {
        message = 'Saved to the local demo case. No message was sent to a person or emergency service.';
        pending = null;
      } else {
        pending.status = result.status;
        pending.message = result.issues?.[0]?.message || 'This change was not accepted.';
      }
      persistPending();
      if (!pending && !pendingSaved) message += ' The old unsent record could not be removed from device storage. Replaying its event ID will not apply it twice.';
      changed();
    }
    function submit(type, payload) {
      if (pending) return;
      const snapshot = service.readCase();
      if (snapshot.case_id !== owner) { message = 'The case changed. Reopen this page before entering a new check-in change.'; changed(); return; }
      const suffix = window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
      const command = { contract_version: '0.1', case_id: snapshot.case_id, event_id: `c11_${suffix}`, expected_case_version: snapshot.case_version, occurred_at: service.readCheckInTime(), channel: 'dashboard', type, payload };
      try { window.StillHereCheckInDemo.apply(snapshot, command, service.readCheckInTime()); }
      catch (error) { message = error.message; changed(); return; }
      pending = { command, status: 'queued_local', message: '' };
      message = '';
      persistPending();
      send();
    }

    function renderHome() {
      const link = document.querySelector('#check-in-home');
      const snapshot = service.readCase();
      const checkIn = snapshot.check_in;
      const openReview = snapshot.follow_ups.some((item) => item.simulation && item.state !== 'outcome_recorded');
      const visible = pending || checkIn.status !== 'not_enrolled' || snapshot.shared_location || openReview;
      link.classList.toggle('is-hidden', !visible);
      link.textContent = pending ? 'Check-ins · a change is still unsent →' : checkIn.status === 'overdue' ? 'Check-ins · no reply recorded →' : checkIn.enrolled && checkIn.status !== 'answered' ? `Your next check-in · ${time(checkIn.schedule.due_at)} →` : openReview ? 'Check-ins · a demo review request is recorded →' : 'Manage check-ins and location sharing →';
    }
    function render() {
      const snapshot = service.readCase();
      const c = snapshot.check_in;
      const schedule = c.schedule;
      const location = snapshot.shared_location;
      const busy = Boolean(pending);
      const disabled = busy ? 'disabled' : '';
      const active = c.enrolled && schedule && !schedule.report;
      const demoOpen = root.querySelector('#check-in-demo-tools')?.open;
      const locationOpen = root.querySelector('#check-in-location')?.open;
      const titles = { not_enrolled: 'Check in when you choose.', scheduled: 'Your next check-in', due: 'Your check-in is due', reminder_attempted: 'Your check-in is due', overdue: 'No reply recorded yet', answered: 'Your reply is recorded', paused: 'Check-ins are paused', canceled: 'Check-ins are stopped' };
      const review = snapshot.follow_ups.filter((item) => item.simulation && item.state !== 'outcome_recorded');
      const pendingDetail = pending?.command.type === 'check_in.reply' ? replies[pending.command.payload.reply] : pending?.command.type === 'check_in.enroll' ? `Due ${time(pending.command.payload.due_at)}` : pending?.command.type === 'check_in.pause' ? pending.command.payload.intent === 'stop' ? 'Stop check-ins' : 'Pause check-ins' : '';
      root.innerHTML = `
        <p class="check-in-feedback" role="status">${escape(message)}</p>
        ${pending ? `<section class="check-in-unsent" aria-labelledby="check-in-unsent-title"><h2 id="check-in-unsent-title">${pending.status === 'conflict' ? 'Review this unsent change' : 'A change is still unsent'}</h2>
          <p><strong>${escape(labels[pending.command.type])}</strong>${pendingDetail ? ` · ${escape(pendingDetail)}` : ''}<br>Entered ${escape(time(pending.command.occurred_at))}.</p>
          <p>${escape(pending.message || 'Saved here until the demo case accepts it.')} ${!pendingSaved ? 'Not saved on this device. Keep this page open.' : 'Stored on this device.'}</p>
          ${pending.command.type === 'check_in.pause' ? '<p>Check-ins are not paused or stopped until this change is accepted.</p>' : ''}
          ${pending.command.type === 'location.clear' ? '<p>Removal is pending. The demo case still holds its previously shared location.</p>' : ''}
          ${pending.command.type === 'location.share' ? '<p>This location has not been added to the demo case.</p>' : ''}
          ${pending.status === 'conflict' ? '<p>Review the current details below. Retrying will use the current case version and keep your original report time and event ID.</p>' : ''}
          <div class="check-in-actions"><button class="button button-primary" data-check-in-action="${pending.status === 'conflict' ? 'reconcile' : 'retry'}">${pending.status === 'conflict' ? 'I’ve reviewed it — retry this change' : 'Retry unsent change'}</button><button class="quiet-link" data-check-in-action="discard">Discard unsent change</button></div></section>` : ''}
        <section class="check-in-panel" aria-labelledby="check-in-state-title">
          <p class="eyebrow">OPTIONAL CHECK-INS</p><h2 id="check-in-state-title">${escape(titles[c.status] || c.status)}</h2>
          ${active ? `<p>Due <strong>${escape(time(schedule.due_at, schedule.time_zone))}</strong>.<br>Grace period ends ${escape(time(schedule.grace_deadline, schedule.time_zone))}.</p>
            ${c.status === 'overdue' ? '<p class="check-in-warning">The grace period has passed. Your condition is unknown. A simulated review request is recorded; no person has been alerted.</p>' : c.status === 'reminder_attempted' ? '<p>A reminder attempt is recorded in the demo only. No text, call, or notification was sent.</p>' : ''}
            <div class="check-in-actions"><button class="button button-primary" data-check-in-action="okay" ${disabled}>I’m okay for now</button><button class="button button-secondary" data-check-in-action="help-reply" ${disabled}>I need help</button><button class="quiet-link" data-check-in-action="later" ${disabled}>Choose a later time</button></div>
            <form id="check-in-later-form" class="check-in-form is-hidden"><fieldset ${disabled}><label for="check-in-later-time">Choose your next check-in</label><select id="check-in-later-time" name="hours">${timeOptions()}</select><p>This answers the current check-in and sets the next one at your selected time.</p><button class="button button-primary" type="submit">Confirm later time</button></fieldset></form>` : ''}
          ${c.last_report ? `<div class="check-in-report"><strong>Your last reply: ${escape(replies[c.last_report.reply])}</strong><br>Reported ${escape(time(c.last_report.reported_at))}.<br>Accepted by the demo ${escape(time(c.last_report.received_at))}.<p>This is your report at that time. It does not verify your current safety.</p></div>` : ''}
          ${!active ? `<p>${c.status === 'answered' ? 'No new check-in is scheduled. Choose another time whenever you want.' : 'Choose a time that works for you. You can use recovery help and finances without check-ins.'}</p>
            <form id="check-in-enroll-form" class="check-in-form"><fieldset ${disabled}>
              <label for="check-in-due-time">Next check-in · ${escape(snapshot.time_zone)}</label><select id="check-in-due-time" name="hours">${timeOptions()}</select>
              <label for="check-in-grace">Grace period after that time</label><select id="check-in-grace" name="grace"><option value="15">15 minutes</option><option value="30" selected>30 minutes</option><option value="60">1 hour</option><option value="120">2 hours</option></select>
              <label class="check-in-consent"><input type="checkbox" name="consent" required><span>I choose this check-in and agree to save it on this device. In this demo, reminders and review requests are simulated.</span></label>
              <button class="button button-primary" type="submit">${c.status === 'not_enrolled' ? 'Start check-ins' : 'Schedule a new check-in'}</button>
            </fieldset></form>` : ''}
          ${c.enrolled ? `<div class="check-in-secondary-actions"><button class="quiet-link" data-check-in-action="pause" ${disabled}>Pause check-ins</button><button class="quiet-link" data-check-in-action="stop" ${disabled}>Stop check-ins</button></div>` : ''}
          ${review.length ? `<p class="check-in-review-note">${review.length} simulated review request${review.length === 1 ? '' : 's'} remains open. No human acknowledgment is recorded. Replying or pausing does not close an open review.</p>` : ''}
        </section>
        <section class="check-in-help" aria-label="Ask for help"><h2>Need help now?</h2><p>In immediate danger, <a href="tel:911">call 911</a>. A demo request does not alert emergency services.</p><div class="check-in-actions"><a class="button button-secondary" href="#chat" data-page-link="chat" data-chat-mode="recovery">Open recovery chat</a><button class="quiet-link" data-check-in-action="help" ${disabled}>Record a help request (demo)</button></div></section>
        <details class="check-in-panel" id="check-in-location" ${locationOpen ? 'open' : ''}><summary>Location for follow-up · ${location ? 'shared in demo' : 'not shared'}</summary>
          <p>This is a separate choice from your city for local notices. Enter a fictional place; no GPS or background tracking is used.</p>
          ${location ? `<div class="check-in-report"><strong>${pending?.command.type === 'location.clear' ? 'Location hidden while removal is pending' : escape(location.place)}</strong><br>Manually entered, last known location.<br>Observed ${escape(time(location.observed_at))}.<p>${Date.parse(service.readCheckInTime()) - Date.parse(location.observed_at) >= 86400000 ? 'At least 24 hours old — stale in this demo.' : 'Less than 24 hours old in the demo.'} It may no longer be current.</p></div><button class="quiet-link" data-check-in-action="clear-location" ${disabled}>Stop sharing and remove this location</button>` : ''}
          <form id="check-in-location-form" class="check-in-form"><fieldset ${disabled}><label for="check-in-place">${location ? 'Update the shared place' : 'Place you want to share'}</label><input id="check-in-place" name="place" maxlength="160" placeholder="Example: a named shelter, city and state" required autocomplete="off">
            <label for="check-in-observed">When were you there? · demo time</label><select id="check-in-observed" name="age"><option value="0">Now</option><option value="1">1 hour ago</option><option value="24">1 day ago</option><option value="48">2 days ago</option></select>
            <label class="check-in-consent"><input type="checkbox" name="consent" required><span>I agree to save this location on this device for this demo case’s follow-up. I can remove it here.</span></label><button class="button button-secondary" type="submit">${location ? 'Update shared location' : 'Share this location'}</button></fieldset></form>
        </details>
        <details class="check-in-panel check-in-demo-tools" id="check-in-demo-tools" ${demoOpen ? 'open' : ''}><summary>Demo controls</summary>
          <p>Demo time: <strong>${escape(time(service.readCheckInTime()))}</strong>. The clock moves only using these controls. No background monitoring runs.</p>
          <div class="check-in-actions"><button class="button button-secondary" data-check-in-action="advance-hour">Advance 1 hour</button>${active && Date.parse(schedule.grace_deadline) >= Date.parse(service.readCheckInTime()) ? '<button class="button button-secondary" data-check-in-action="advance-overdue">Move past grace period</button>' : ''}</div>
          <label class="check-in-consent"><input type="checkbox" id="check-in-offline-demo" ${offlineDemo ? 'checked' : ''}><span>Simulate offline sending. Changes stay unsent until I turn this off and retry.</span></label>
          <p>Case version ${snapshot.case_version}. ${navigator.onLine === false ? 'Your browser also reports being offline.' : 'This page uses the local mock service.'} Grace periods and the 24-hour location label are demo settings.</p>
        </details>`;
      renderHome();
    }

    root.addEventListener('submit', (event) => {
      event.preventDefault();
      if (pending) return;
      const fields = new FormData(event.target);
      const snapshot = service.readCase();
      if (event.target.id === 'check-in-enroll-form') submit('check_in.enroll', { consent: fields.get('consent') === 'on', due_at: after(fields.get('hours')), time_zone: snapshot.time_zone, grace_minutes: Number(fields.get('grace')), channel: 'in_app_simulation' });
      if (event.target.id === 'check-in-later-form') submit('check_in.reply', { schedule_id: snapshot.check_in.schedule.id, occurrence_id: snapshot.check_in.schedule.occurrence_id, reply: 'check_later', new_due_at: after(fields.get('hours')) });
      if (event.target.id === 'check-in-location-form') submit('location.share', { consent: fields.get('consent') === 'on', scope: 'case_follow_up', place: String(fields.get('place')).trim(), observed_at: iso(Date.parse(service.readCheckInTime()) - Number(fields.get('age')) * 3600000) });
    });
    root.addEventListener('click', (event) => {
      const action = event.target.closest('[data-check-in-action]')?.dataset.checkInAction;
      if (!action) return;
      if (action === 'retry') { send(); return; }
      if (action === 'reconcile' && pending) {
        pending.command.expected_case_version = service.readCase().case_version;
        pending.status = 'queued_local';
        persistPending();
        send();
        return;
      }
      if (action === 'discard') {
        const discarded = pending;
        pending = null;
        persistPending();
        if (!pendingSaved) pending = discarded;
        message = pendingSaved ? 'Unsent change discarded. The demo case was not changed.' : 'Unable to remove the unsent change from device storage. Keep this page open and try discarding again.';
        changed();
        return;
      }
      if (action.startsWith('advance-')) {
        const schedule = service.readCase().check_in.schedule;
        const target = action === 'advance-overdue' ? iso(Date.parse(schedule.grace_deadline) + 60000) : after(1);
        const result = service.advanceCheckInClock(target);
        message = result.status === 'applied' ? 'Demo time advanced. Any reminder or review is simulated.' : result.issues[0].message;
        changed();
        return;
      }
      if (pending) return;
      const schedule = service.readCase().check_in.schedule;
      if (action === 'later') {
        root.querySelector('#check-in-later-form').classList.remove('is-hidden');
        root.querySelector('#check-in-later-time').focus();
      }
      if (action === 'okay' || action === 'help-reply') submit('check_in.reply', { schedule_id: schedule.id, occurrence_id: schedule.occurrence_id, reply: action === 'okay' ? 'okay_for_now' : 'need_help' });
      if (action === 'pause' || action === 'stop') submit('check_in.pause', { intent: action });
      if (action === 'help') submit('help.request', { message: 'I need help.', ...(schedule ? { occurrence_id: schedule.occurrence_id } : {}) });
      if (action === 'clear-location') submit('location.clear', { intent: 'stop_sharing' });
    });
    root.addEventListener('change', (event) => {
      if (event.target.id !== 'check-in-offline-demo') return;
      offlineDemo = event.target.checked;
      message = offlineDemo ? 'Offline simulation is on. Check-in and location changes will stay unsent.' : 'Offline simulation is off. Retry any unsent change when ready.';
      changed();
    });
    function connectionChanged() {
      message = navigator.onLine === false ? 'Your browser reports being offline. Changes will remain unsent until you retry.' : offlineDemo ? 'Your connection is back. Offline simulation is still on.' : 'Your connection is back. Retry any unsent change when ready.';
      root.querySelector('.check-in-feedback')?.replaceChildren(document.createTextNode(message));
      onChange();
    }
    window.addEventListener('online', connectionChanged);
    window.addEventListener('offline', connectionChanged);
    return Object.freeze({ render, renderHome });
  }

  window.StillHereCheckInControls = Object.freeze({ mount });
})();
// Built by Raneem Mousa
