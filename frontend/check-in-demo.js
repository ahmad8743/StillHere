/* C11 fixture behavior only. P1 owns the real check-in engine and receivers. */
(() => {
  const types = ['check_in.enroll', 'check_in.reply', 'check_in.pause', 'help.request', 'location.share', 'location.clear'];
  const copy = (value) => structuredClone(value);
  const instant = (value) => {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value) || !Number.isFinite(Date.parse(value))) return false;
    return new Date(value).toISOString().replace('.000Z', 'Z') === value;
  };
  function requireValue(condition, message) { if (!condition) throw new TypeError(message); }
  function fields(payload, allowed) {
    requireValue(Object.keys(payload).every((key) => allowed.includes(key)), 'This change contains an unsupported field.');
  }
  function futureTime(value, now) {
    requireValue(instant(value) && Date.parse(value) > Date.parse(now), 'Choose a check-in time after the current demo time.');
  }
  function occurrence(eventId, dueAt, zone, grace) {
    return {
      id: `schedule_${eventId}`, occurrence_id: `occurrence_${eventId}`,
      due_at: dueAt, time_zone: zone, grace_minutes: grace,
      grace_deadline: new Date(Date.parse(dueAt) + grace * 60000).toISOString().replace('.000Z', 'Z'),
      channel: 'in_app_simulation', reminder_attempt_id: null, review_id: null, report: null
    };
  }
  function review(snapshot, occurrenceId, reason, now, report = null, requestId = occurrenceId) {
    const existing = snapshot.follow_ups.find((item) => item.simulation && item.occurrence_id === occurrenceId && item.state !== 'outcome_recorded');
    const item = existing || {
      id: `review_${requestId}`, occurrence_id: occurrenceId, state: 'requested',
      reason, condition: 'unknown', requested_at: now, simulation: true
    };
    if (!existing) snapshot.follow_ups.push(item);
    if (report) item.last_report = copy(report);
    return item.id;
  }

  function apply(original, command, receivedAt) {
    const snapshot = copy(original);
    const checkIn = snapshot.check_in;
    const p = command.payload;
    requireValue(types.includes(command.type) && p && typeof p === 'object' && !Array.isArray(p), 'Choose a supported check-in change.');
    requireValue(instant(receivedAt) && instant(command.occurred_at) && Date.parse(command.occurred_at) <= Date.parse(receivedAt), 'The report time must be a valid demo time, no later than receipt.');
    if (command.type === 'check_in.enroll') {
      fields(p, ['consent', 'due_at', 'time_zone', 'grace_minutes', 'channel']);
      requireValue(p.consent === true, 'Check-ins need your explicit permission.');
      requireValue(p.time_zone === snapshot.time_zone && p.channel === 'in_app_simulation', 'Use the case time zone and simulated in-app channel.');
      requireValue(Number.isInteger(p.grace_minutes) && p.grace_minutes >= 15 && p.grace_minutes <= 1440, 'Choose a grace period from 15 minutes to one day.');
      requireValue(!checkIn.enrolled || checkIn.status === 'answered', 'Reply or pause the current check-in before starting another.');
      futureTime(p.due_at, receivedAt);
      if (checkIn.schedule) checkIn.history = [...(checkIn.history || []), copy(checkIn.schedule)];
      checkIn.schedule = occurrence(command.event_id, p.due_at, p.time_zone, p.grace_minutes);
      Object.assign(checkIn, { enrolled: true, status: 'scheduled', consent: { granted_at: command.occurred_at, simulation: true } });
    } else if (command.type === 'check_in.reply') {
      fields(p, ['schedule_id', 'occurrence_id', 'reply', 'new_due_at']);
      const schedule = checkIn.schedule;
      requireValue(schedule && p.schedule_id === schedule.id && p.occurrence_id === schedule.occurrence_id, 'This reply belongs to a different check-in. Review the latest check-in first.');
      requireValue(!schedule.report, 'This check-in already has a reply. Choose another time or record a new help request.');
      requireValue(['okay_for_now', 'need_help', 'check_later'].includes(p.reply), 'Choose one of the listed replies.');
      if (p.reply === 'check_later') {
        requireValue(checkIn.enrolled, 'Start a new check-in to resume after a pause.');
        futureTime(p.new_due_at, receivedAt);
      } else requireValue(p.new_due_at === undefined, 'Only a later-time reply can set a new check-in time.');
      const report = { event_id: command.event_id, occurrence_id: schedule.occurrence_id, reply: p.reply, reported_at: command.occurred_at, received_at: receivedAt, simulation: true };
      schedule.report = report;
      checkIn.last_report = copy(report);
      if (schedule.review_id) {
        const existing = snapshot.follow_ups.find((item) => item.id === schedule.review_id);
        if (existing) existing.last_report = copy(report);
      }
      if (p.reply === 'need_help') schedule.review_id = review(snapshot, schedule.occurrence_id, 'help_requested', receivedAt, report, command.event_id);
      if (p.reply === 'check_later') {
        checkIn.history = [...(checkIn.history || []), copy(schedule)];
        checkIn.schedule = occurrence(command.event_id, p.new_due_at, schedule.time_zone, schedule.grace_minutes);
        checkIn.status = 'scheduled';
      } else if (checkIn.enrolled) checkIn.status = 'answered';
    } else if (command.type === 'check_in.pause') {
      fields(p, ['intent']);
      requireValue(['pause', 'stop'].includes(p.intent), 'Choose pause or stop.');
      checkIn.enrolled = false;
      checkIn.status = p.intent === 'stop' ? 'canceled' : 'paused';
      if (checkIn.schedule) checkIn.schedule.canceled_at = receivedAt;
    } else if (command.type === 'help.request') {
      fields(p, ['message', 'occurrence_id']);
      requireValue(typeof p.message === 'string' && p.message.trim().length > 0 && p.message.length <= 500, 'Enter a short help request.');
      requireValue(p.occurrence_id === undefined || p.occurrence_id === checkIn.schedule?.occurrence_id, 'Review the latest check-in before linking this request.');
      const related = p.occurrence_id || `help_${command.event_id}`;
      const report = { event_id: command.event_id, reply: 'need_help', message: p.message.trim(), reported_at: command.occurred_at, received_at: receivedAt, simulation: true };
      const reviewId = review(snapshot, related, 'help_requested', receivedAt, report, command.event_id);
      if (p.occurrence_id) checkIn.schedule.review_id = reviewId;
    } else if (command.type === 'location.share') {
      fields(p, ['consent', 'scope', 'place', 'observed_at']);
      requireValue(p.consent === true && p.scope === 'case_follow_up', 'Location sharing needs separate, explicit permission for case follow-up.');
      requireValue(typeof p.place === 'string' && p.place.trim().length > 0 && p.place.length <= 160, 'Enter a place with up to 160 characters.');
      requireValue(instant(p.observed_at) && Date.parse(p.observed_at) <= Date.parse(receivedAt), 'The location observation time cannot be in the future.');
      snapshot.shared_location = {
        place: p.place.trim(), source: 'manual', observed_at: p.observed_at, received_at: receivedAt,
        permission: { scope: p.scope, granted_at: command.occurred_at }, simulation: true
      };
    } else if (command.type === 'location.clear') {
      fields(p, ['intent']);
      requireValue(p.intent === 'stop_sharing', 'Confirm that you want to stop sharing this location.');
      snapshot.shared_location = null;
    }
    return snapshot;
  }

  function advance(original, now) {
    requireValue(instant(now), 'Choose a valid demo time.');
    const snapshot = copy(original);
    const checkIn = snapshot.check_in;
    const schedule = checkIn.schedule;
    if (!checkIn.enrolled || !schedule || schedule.report || Date.parse(now) < Date.parse(schedule.due_at)) return snapshot;
    if (!schedule.reminder_attempt_id) {
      schedule.reminder_attempt_id = `reminder_${schedule.occurrence_id}`;
      checkIn.attempts.push({ id: schedule.reminder_attempt_id, occurrence_id: schedule.occurrence_id, attempted_at: now, channel: 'in_app_simulation', simulation: true });
    }
    if (Date.parse(now) >= Date.parse(schedule.grace_deadline)) {
      checkIn.status = 'overdue';
      schedule.review_id = schedule.review_id || review(snapshot, schedule.occurrence_id, 'overdue_condition_unknown', now);
    } else checkIn.status = 'reminder_attempted';
    return snapshot;
  }

  window.StillHereCheckInDemo = Object.freeze({ types, apply, advance });
})();
// Built by Raneem Mousa
