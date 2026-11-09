import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/features/chat/chat_flow.dart';
import 'package:roost_mobile/features/chat/computer_steps.dart';
import 'package:roost_mobile/features/chat/run_steps.dart';

Message m(String id, String role, String body,
        {String kind = 'text', String at = '2026-10-23T20:15:00Z', int seq = 1}) =>
    Message(
        id: id,
        threadId: 't1',
        role: role,
        body: body,
        seq: seq,
        createdAt: at,
        kind: kind,
        authorBotId: role == 'bot' ? 'b1' : null);

Message program(String id, {String at = '2026-10-23T20:15:10Z'}) => m(
    id,
    'system',
    jsonEncode({
      'op': 'run',
      'command': 'curl -sI -m 10 https://web.whatsapp.com | head -n 1',
      'exit_code': 0,
      'output': 'HTTP/2 200',
    }),
    kind: 'program_activity',
    at: at);

Message approval(String id, String card, {String at = '2026-10-23T20:15:05Z'}) =>
    m(id, 'bot', jsonEncode({'card_id': card, 'kind': 'ask', 'steps': ['Run a program: curl']}),
        kind: 'approval', at: at);

ActivityRun run(String id,
    {bool done = false, String at = '2026-10-23T20:15:01Z', int steps = 1}) {
  var r = ActivityRun.empty(runId: id, botId: 'b1', threadId: 't1');
  for (var i = 1; i <= steps; i++) {
    r = r.withStep(RunStep(
        step: i, kind: 'search', line: 'Browsing web.whatsapp.com', at: at, state: 'start'));
  }
  return done ? r.finished(at) : r;
}

final bot = Bot.fromJson({'id': 'b1', 'name': 'Gela', 'status': 'on_it', 'activity': 'opening WhatsApp Web'});

List<String> shape(ChatFlow flow) => [
      for (final i in flow.items)
        switch (i) {
          Message x => x.id,
          ActivityItem a => 'run:${a.run.runId}${a.live ? '*' : ''}',
          ComputerRun c => 'computer:${c.runId}',
          LivePillItem _ => 'pill',
          _ => '?',
        }
    ];

void main() {
  test('technical lines leave the chat; a card still waiting for you stays', () {
    final flow = buildChatFlow(messages: [
      m('u1', 'user', 'open whatsapp web'),
      approval('a1', 'c1'),
      m('ans', 'user', 'Yes: Run a program: curl', kind: 'card_answer', at: '2026-10-23T20:15:06Z'),
      program('p1'),
      m('res', 'system', 'ok', kind: 'approval_result', at: '2026-10-23T20:15:11Z'),
      approval('a2', 'c2', at: '2026-10-23T20:15:20Z'),
    ], answers: {'c1': 'Yes: Run a program: curl'});
    expect(shape(flow), ['u1', 'run:a1', 'a2']);
    final grouped = flow.items[1] as ActivityItem;
    expect(grouped.live, isFalse);
    expect(grouped.notes.map((n) => n.line), ['You said yes', 'Ran a program']);
    expect(grouped.notes.last.raw, contains('curl'));
    expect(grouped.notes.map((n) => n.line).join(), isNot(contains('curl')));
  });

  test('a reply loses its On it lead; one that is only the lead keeps its words; Continuing goes', () {
    final flow = buildChatFlow(messages: [
      m('u1', 'user', 'hi'),
      m('b1', 'bot', 'On it: opening WhatsApp Web in my browser.'),
      m('b2', 'bot', 'Continuing: opening WhatsApp Web.'),
      m('b3', 'bot', 'On it: checking.\n\nYou have two new messages.'),
    ]);
    expect(shape(flow), ['u1', 'b1', 'b3']);
    expect(flow.texts['b1'], 'Opening WhatsApp Web in my browser.');
    expect(flow.texts['b3'], 'You have two new messages.');
  });

  test('a reply still being written with only its lead is the working line\'s words, not a bubble', () {
    final flow = buildChatFlow(
      messages: [m('u1', 'user', 'hi'), m('p1', 'bot', '', seq: 0)],
      streaming: {'p1': 'On it: checking your week.'},
      bot: bot,
    );
    expect(shape(flow), ['u1', 'pill']);
    expect((flow.items.last as LivePillItem).words, 'checking your week.');
  });

  test('once the answer streams it shows alone and the working line steps aside', () {
    final flow = buildChatFlow(
      messages: [m('u1', 'user', 'hi'), m('p1', 'bot', '', seq: 0)],
      streaming: {'p1': 'On it: checking your week.\n\nTwo meetings'},
      bot: bot,
    );
    expect(shape(flow), ['u1', 'p1']);
    expect(flow.texts['p1'], 'Two meetings');
  });

  test('a live run sits after your message, takes its technical lines, and shows its computer card', () {
    final computer = const ComputerRun(
        runId: 'r1', botId: 'b1', threadId: 't1', steps: [
          ComputerStep(step: 1, kind: 'look', line: 'Looked', at: '2026-10-23T20:15:02Z'),
        ], count: 1);
    final other = const ComputerRun(
        runId: 'r0', botId: 'b1', threadId: 't1', steps: [
          ComputerStep(step: 1, kind: 'look', line: 'Looked', at: '2026-10-23T20:00:00Z'),
        ], count: 1, done: true);
    final flow = buildChatFlow(
      messages: [
        m('u0', 'user', 'earlier', at: '2026-10-23T19:59:00Z'),
        m('u1', 'user', 'open whatsapp web'),
        program('p1'),
      ],
      runs: [run('r1')],
      computerRuns: [other, computer],
      bot: bot,
    );
    expect(shape(flow), ['u0', 'computer:r0', 'u1', 'run:r1*']);
    final live = flow.items.last as ActivityItem;
    expect(live.computer?.runId, 'r1');
    expect(live.notes.single.line, 'Ran a program');
  });

  test('On it with no run yet shows the pill at the end; a resting bot shows none', () {
    final flow = buildChatFlow(messages: [m('u1', 'user', 'hi')], bot: bot);
    expect(shape(flow), ['u1', 'pill']);
    final resting = buildChatFlow(
        messages: [m('u1', 'user', 'hi')],
        bot: Bot.fromJson({'id': 'b1', 'name': 'Gela', 'status': 'resting'}));
    expect(shape(resting), ['u1']);
  });

  test('a finished run reads as one line and keeps its place', () {
    final flow = buildChatFlow(messages: [
      m('u1', 'user', 'hi'),
      m('b1', 'bot', 'Done, here it is.', at: '2026-10-23T20:16:00Z'),
    ], runs: [run('r1', done: true)]);
    expect(shape(flow), ['u1', 'run:r1', 'b1']);
  });

  englishFixTests();
}

Message englishFix(String id, String forMessage, {String at = '2026-10-23T20:15:30Z'}) => m(
    id,
    'activity',
    jsonEncode({
      'message_id': forMessage,
      'said': 'I has a plan',
      'corrected': 'I have a plan',
      'fixes': [
        {'wrong': 'has', 'right': 'have'}
      ],
    }),
    kind: 'english_fix',
    at: at);

void englishFixTests() {
  test('an english_fix line sits right under the message it names, never inside a run', () {
    final flow = buildChatFlow(messages: [
      m('u1', 'user', 'I has a plan'),
      m('b1', 'bot', 'Great, tell me.', at: '2026-10-23T20:15:20Z'),
      englishFix('f1', 'u1'),
    ], runs: [run('r1', done: true)]);
    expect(shape(flow), ['u1', 'f1', 'run:r1', 'b1']);
    final grouped = flow.items[2] as ActivityItem;
    expect(grouped.notes, isEmpty);
  });

  test('an english_fix for a message that is not loaded stays at its own place', () {
    final flow = buildChatFlow(messages: [
      m('u1', 'user', 'hi'),
      m('b1', 'bot', 'Hello.', at: '2026-10-23T20:15:20Z'),
      englishFix('f1', 'u-gone'),
    ]);
    expect(shape(flow), ['u1', 'b1', 'f1']);
  });

  test('an unreadable english_fix body stays a message at its own place', () {
    final flow = buildChatFlow(messages: [
      m('u1', 'user', 'hi'),
      m('f1', 'activity', 'not json', kind: 'english_fix', at: '2026-10-23T20:15:30Z'),
    ]);
    expect(shape(flow), ['u1', 'f1']);
  });

  // Owner, 2026-10-31: two routine lines three hours apart read "Worked for 180 min 15 s · 2 steps".
  test('routine and question lines are their own quiet lines, never a run of steps', () {
    final flow = buildChatFlow(messages: [
      m('u1', 'user', 'what is on today'),
      m('b1', 'bot', 'Here are your tasks.', at: '2026-10-31T11:37:43Z'),
      m('n1', 'activity', 'Ran Check jobs · nothing new', kind: 'routine_note', at: '2026-10-31T14:00:24Z'),
      m('n2', 'activity', 'Ran Check jobs · nothing new', kind: 'routine_note', at: '2026-10-31T17:00:40Z'),
      m('q1', 'activity', 'Noted a question', kind: 'question_note', at: '2026-10-31T17:05:00Z'),
    ]);
    expect(shape(flow), ['u1', 'b1', 'n1', 'n2', 'q1']);
    expect(flow.items.whereType<ActivityItem>(), isEmpty);
  });
}
