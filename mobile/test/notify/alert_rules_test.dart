import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/notify/alert_rules.dart';
import 'package:roost_mobile/notify/notify_prefs.dart';

// 10:00 UTC on 23 Oct 2026 is 12:00 in Madrid (CEST).
final noon = DateTime.utc(2026, 10, 23, 10);
// 22:30 UTC is 00:30 in Madrid.
final lateNight = DateTime.utc(2026, 10, 23, 22, 30);

Map<String, dynamic> snapshot({bool notify = true}) => {
      'type': 'snapshot',
      'bots': [
        {'id': 'b1', 'name': 'Chief', 'notify': notify, 'status': 'resting', 'avatar': null},
      ],
    };

Map<String, dynamic> message(String id, String kind, Object body,
        {String role = 'bot', bool tainted = false, String bot = 'b1'}) =>
    {
      'type': 'message',
      'thread_id': 't1',
      'message': {
        'id': id,
        'thread_id': 't1',
        'role': role,
        'kind': kind,
        'body': body is String ? body : jsonEncode(body),
        'tainted': tainted,
        'author_bot_id': bot,
      },
    };

const away = AppFocus.away;
const prefs = NotifyPrefs(stayConnected: true);

AlertBook booted({bool notify = true}) =>
    AlertBook()..take(snapshot(notify: notify), prefs: prefs, focus: away, now: noon);

void main() {
  test('an Ask card: "Chief needs your OK" with the step, once per card', () {
    final book = booted();
    final card = message('m1', 'approval', {
      'card_id': 'c1',
      'kind': 'ask',
      'steps': ["Click 'Send'"],
    });
    final alert = book.take(card, prefs: prefs, focus: away, now: noon)!;
    expect(alert.kind, AlertKind.needsOk);
    expect(alert.title, 'Chief needs your OK');
    expect(alert.body, "Click 'Send'");
    expect(alert.botId, 'b1');
    expect(alert.key, 'card:c1');
    // The same card again (a resume, a second frame) is not a second alert.
    expect(book.take(card, prefs: prefs, focus: away, now: noon), isNull);
  });

  test('a Proposal card and a sign-in card also need you', () {
    final book = booted();
    final plan = book.take(
        message('m1', 'approval', {'card_id': 'c2', 'kind': 'plan', 'steps': ['a', 'b', 'c']}),
        prefs: prefs, focus: away, now: noon)!;
    expect(plan.title, 'Chief needs your OK');
    expect(plan.body, '3 changes to review');
    final signIn = book.take(
        message('m2', 'stuck', {'card_id': 's1', 'host': 'upwork.com', 'sign_in': true, 'line': 'x'}),
        prefs: prefs, focus: away, now: noon)!;
    expect(signIn.kind, AlertKind.needsOk);
    expect(signIn.title, 'Chief needs you');
    expect(signIn.body, 'Sign in to upwork.com');
    final stuck = book.take(
        message('m3', 'stuck', {'card_id': 's2', 'host': 'x.com', 'sign_in': false, 'line': 'Stuck on x.com: a human check.'}),
        prefs: prefs, focus: away, now: noon)!;
    expect(stuck.body, 'Stuck on x.com: a human check.');
    final skill = book.take(message('m4', 'skill_proposal', {'proposal_id': 'p1', 'name': 'Post'}),
        prefs: prefs, focus: away, now: noon)!;
    expect(skill.kind, AlertKind.needsOk);
    expect(skill.body, 'A skill to save: Post');
  });

  test('a Report and a task reminder', () {
    final book = booted();
    final report = book.take(
        message('m1', 'report', {'source': 'routine', 'headline': 'Inbox checked', 'text': 'Two new messages.\nMore.'}),
        prefs: prefs, focus: away, now: noon)!;
    expect(report.kind, AlertKind.report);
    expect(report.title, 'Chief: Inbox checked');
    expect(report.body, 'Two new messages.');
    final reminder = book.take(
        message('m2', 'report', {'source': 'reminder', 'headline': 'Reminder: Call Iurie', 'text': 'Call Iurie · reminder for 12:00.'}),
        prefs: prefs, focus: away, now: noon)!;
    expect(reminder.kind, AlertKind.reminder);
    expect(reminder.title, 'Reminder: Call Iurie');
  });

  test('a streamed reply alerts once it is done, with its first line', () {
    final book = booted();
    expect(book.take(message('m9', 'text', ''), prefs: prefs, focus: away, now: noon), isNull);
    for (final part in ['James ended ', 'the contract.\nNo review yet.']) {
      expect(
          book.take({'type': 'text_delta', 'thread_id': 't1', 'message_id': 'm9', 'delta': part},
              prefs: prefs, focus: away, now: noon),
          isNull);
    }
    final done = book.take({'type': 'message_done', 'thread_id': 't1', 'message_id': 'm9'},
        prefs: prefs, focus: away, now: noon)!;
    expect(done.kind, AlertKind.reply);
    expect(done.title, 'Chief');
    expect(done.body, 'James ended the contract.');
  });

  test('text from web content reads as the text alone (owner, 2026-11-05: the prefix was noise)', () {
    final book = booted();
    final r = book.take(message('m1', 'text', 'Found 3 jobs.', tainted: true),
        prefs: prefs, focus: away, now: noon)!;
    expect(r.body, 'Found 3 jobs.');
  });

  Map<String, dynamic> inThread(Map<String, dynamic> frame, String thread) => {
        ...frame,
        'thread_id': thread,
        'message': {...(frame['message'] as Map), 'thread_id': thread},
      };

  test("a routine run's own reply in its run log never alerts; its Report does", () {
    final book = booted();
    book.take(inThread(message('r0', 'routine', 'Check WhatsApp.', role: 'user', bot: 'x'), 'log1'),
        prefs: prefs, focus: away, now: noon);
    expect(book.take(inThread(message('m1', 'text', 'On it: checking…'), 'log1'),
        prefs: prefs, focus: away, now: noon), isNull);
    // Streamed into the run log: nothing either.
    book.take(inThread(message('m2', 'text', ''), 'log1'), prefs: prefs, focus: away, now: noon);
    book.take({'type': 'text_delta', 'message_id': 'm2', 'delta': '[nothing new]'},
        prefs: prefs, focus: away, now: noon);
    expect(book.take({'type': 'message_done', 'thread_id': 'log1', 'message_id': 'm2'},
        prefs: prefs, focus: away, now: noon), isNull);
    // A card the run raises there still needs you.
    expect(book.take(inThread(message('m3', 'approval', {'card_id': 'c9', 'kind': 'ask', 'steps': ['Open x']}), 'log1'),
        prefs: prefs, focus: away, now: noon)?.kind, AlertKind.needsOk);
    // The bot's own chat still alerts.
    expect(book.take(message('m4', 'text', 'Hi.'), prefs: prefs, focus: away, now: noon), isNotNull);
  });

  test('long text is cut to one short line', () {
    final book = booted();
    final r = book.take(message('m1', 'text', 'x' * 400), prefs: prefs, focus: away, now: noon)!;
    expect(r.body.length, lessThanOrEqualTo(alertBodyMax));
    expect(r.body.endsWith('…'), isTrue);
  });

  test('your own lines and quiet lines never alert', () {
    final book = booted();
    expect(book.take(message('m1', 'text', 'hi', role: 'user'), prefs: prefs, focus: away, now: noon), isNull);
    expect(book.take(message('m2', 'memory_note', {'text': 'x'}), prefs: prefs, focus: away, now: noon), isNull);
    expect(book.take(message('m3', 'reaction', {'key': 'x'}), prefs: prefs, focus: away, now: noon), isNull);
  });

  test("the chat you are looking at doesn't alert; replies wait for the app to be away", () {
    final book = booted();
    const inChief = AppFocus(visible: true, openChatBotId: 'b1');
    const elsewhere = AppFocus(visible: true, openChatBotId: null);
    final card = message('m1', 'approval', {'card_id': 'c1', 'kind': 'ask', 'steps': ['x']});
    expect(book.take(card, prefs: prefs, focus: inChief, now: noon), isNull);
    final card2 = message('m2', 'approval', {'card_id': 'c2', 'kind': 'ask', 'steps': ['x']});
    expect(book.take(card2, prefs: prefs, focus: elsewhere, now: noon), isNotNull);
    expect(book.take(message('m3', 'text', 'hi'), prefs: prefs, focus: elsewhere, now: noon), isNull);
    expect(book.take(message('m4', 'text', 'hi'), prefs: prefs, focus: away, now: noon), isNotNull);
  });

  test("each kind has its own switch, and a bot's own switch counts", () {
    final book = booted();
    const noReports = NotifyPrefs(stayConnected: true, reports: false);
    expect(
        book.take(message('m1', 'report', {'source': 'routine', 'headline': 'h', 'text': 't'}),
            prefs: noReports, focus: away, now: noon),
        isNull);
    final muted = booted(notify: false);
    expect(muted.take(message('m2', 'text', 'hi'), prefs: prefs, focus: away, now: noon), isNull);
  });

  test('quiet hours (Madrid) hush everything but your own reminders', () {
    final book = booted();
    const quiet = NotifyPrefs(stayConnected: true, quietOn: true, quietFrom: 23 * 60, quietTo: 7 * 60);
    expect(book.take(message('m1', 'text', 'hi'), prefs: quiet, focus: away, now: lateNight), isNull);
    expect(
        book.take(message('m2', 'report', {'source': 'reminder', 'headline': 'Reminder: x', 'text': 't'}),
            prefs: quiet, focus: away, now: lateNight),
        isNotNull);
    expect(book.take(message('m3', 'text', 'hi'), prefs: quiet, focus: away, now: noon), isNotNull);
  });

  test('a message from an unknown bot is named plainly', () {
    final book = AlertBook();
    final r = book.take(message('m1', 'text', 'hi', bot: 'zz'), prefs: prefs, focus: away, now: noon)!;
    expect(r.title, 'A bot');
  });

  test('the alert id is stable and positive', () {
    final book = booted();
    final a = book.take(message('m1', 'text', 'hi'), prefs: prefs, focus: away, now: noon)!;
    expect(a.id, alertIdFor('msg:m1'));
    expect(a.id, greaterThan(0));
  });

  test("an alert knows its bot's avatar from the snapshot", () {
    final book = AlertBook()
      ..take({
        'type': 'snapshot',
        'bots': [
          {'id': 'b1', 'name': 'Gela', 'notify': true, 'avatar': {'shape': 'cheeky', 'color': '#8b5cf6'}},
        ],
      }, prefs: prefs, focus: away, now: noon);
    final alert = book.take(message('m9', 'text', 'Hello'), prefs: prefs, focus: away, now: noon)!;
    expect(alert.avatar!.shape, 'cheeky');
    expect(alert.avatar!.color, '#8b5cf6');
  });
}
