import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/features/chat/run_steps.dart';

Map<String, dynamic> stepFrame(int n,
        {String kind = 'search',
        String line = 'Browsing web.whatsapp.com',
        String state = 'start',
        String run = 'r1',
        String at = '2026-10-23T20:15:00Z',
        String? host = 'web.whatsapp.com'}) =>
    {
      'type': 'run_step',
      'bot_id': 'b1',
      'thread_id': 't1',
      'run_id': run,
      'step': n,
      'kind': kind,
      'line': line,
      'host': host,
      'at': at,
      'state': state,
    };

void main() {
  test('a run_step frame starts a run in its chat', () {
    final runs = applyRunFrame(const {}, stepFrame(1));
    final run = runs['t1']!.single;
    expect(run.runId, 'r1');
    expect(run.current.line, 'Browsing web.whatsapp.com');
    expect(run.current.kind, 'search');
    expect(run.done, isFalse);
  });

  test('the same step again replaces it (start then done)', () {
    var runs = applyRunFrame(const {}, stepFrame(1));
    runs = applyRunFrame(runs, stepFrame(1, state: 'done'));
    final run = runs['t1']!.single;
    expect(run.count, 1);
    expect(run.current.state, 'done');
  });

  test('an unknown kind reads as other; a broken frame is ignored', () {
    final runs = applyRunFrame(const {}, stepFrame(1, kind: 'warp'));
    expect(runs['t1']!.single.current.kind, 'other');
    final same = applyRunFrame(runs, {'type': 'run_step', 'bot_id': 'b1'});
    expect(identical(same, runs), isTrue);
  });

  test('the bot going back to resting ends its run, with an end time', () {
    var runs = applyRunFrame(const {}, stepFrame(1));
    runs = applyRunFrame(
        runs,
        stepFrame(2,
            kind: 'program',
            line: 'Running a program',
            at: '2026-10-23T20:15:30Z'));
    runs = applyRunFrame(runs, {
      'type': 'bot_status',
      'bot_id': 'b1',
      'status': 'resting',
      'at': '2026-10-23T20:15:42Z',
    });
    final run = runs['t1']!.single;
    expect(run.done, isTrue);
    expect(doneWords(run), 'Worked for 42 s · 2 steps');
  });

  test('a run of only thinking says Thought for', () {
    var runs = applyRunFrame(
        const {}, stepFrame(1, kind: 'think', line: 'Thinking', host: null));
    runs = applyRunFrame(
        runs,
        stepFrame(2,
            kind: 'think',
            line: 'Thinking',
            host: null,
            at: '2026-10-23T20:15:04Z'));
    runs = applyRunFrame(
        runs, {'type': 'bot_status', 'bot_id': 'b1', 'status': 'resting'});
    expect(doneWords(runs['t1']!.single), 'Thought for 4 s');
  });

  test('a new run for the bot ends the one before', () {
    var runs = applyRunFrame(const {}, stepFrame(1));
    runs = applyRunFrame(runs, stepFrame(1, run: 'r2'));
    expect(runs['t1']!.first.done, isTrue);
    expect(runs['t1']!.last.done, isFalse);
  });

  test('the snapshot brings a running run back, leniently', () {
    final runs = applyRunFrame(const {}, {
      'type': 'snapshot',
      'bots': [
        {
          'id': 'b1',
          'status': 'on_it',
          'run_steps': [
            {...stepFrame(1)}..remove('bot_id'),
          ],
        },
        {'id': 'b2', 'status': 'resting'},
      ],
    });
    expect(runs['t1']!.single.done, isFalse);
  });

  test('the server snapshot\'s top-level run_steps map brings it back', () {
    final runs = applyRunFrame(const {}, {
      'type': 'snapshot',
      'bots': [
        {'id': 'b1', 'status': 'on_it'},
      ],
      'run_steps': {
        'b1': [stepFrame(1), stepFrame(2)],
      },
    });
    expect(runs['t1']!.single.done, isFalse);
  });

  // Owner, 2026-11-04: the bot's words between steps belong inside the steps, never as chat bubbles.
  group('notes', () {
    Map<String, dynamic> noteFrame(int n, String line, {bool tainted = false, String at = '2026-10-23T20:15:05Z'}) =>
        {...stepFrame(n, kind: 'note', line: line, state: 'done', at: at, host: null), 'tainted': tainted};

    test('a note keeps its kind and its Web mark', () {
      final runs = applyRunFrame(const {}, noteFrame(1, 'Search is done.', tainted: true));
      final step = runs['t1']!.single.current;
      expect(step.kind, 'note');
      expect(step.tainted, isTrue);
      expect(step.isNote, isTrue);
    });

    test('the pill says the newest note while a step runs, and the robot acts the step out', () {
      var runs = applyRunFrame(const {}, stepFrame(1, kind: 'think', line: 'Thinking', state: 'done'));
      runs = applyRunFrame(runs, noteFrame(2, "Search is done. I'm picking the Acme job."));
      runs = applyRunFrame(runs, stepFrame(3, kind: 'read', line: 'Opened upwork.com', at: '2026-10-23T20:15:06Z'));
      final run = runs['t1']!.single;
      expect(run.pillLine, "Search is done. I'm picking the Acme job.");
      expect(run.pillKind, 'read');
      runs = applyRunFrame(runs,
          stepFrame(4, kind: 'message', line: 'Writing the reply', at: '2026-10-23T20:15:09Z'));
      expect(runs['t1']!.single.pillLine, 'Writing the reply');
    });

    test('notes are not counted as steps, and a run of notes alone only thought', () {
      var runs = applyRunFrame(const {}, noteFrame(1, 'First the search.', at: '2026-10-23T20:15:00Z'));
      runs = applyRunFrame(runs, stepFrame(2, state: 'done', at: '2026-10-23T20:15:02Z'));
      runs = applyRunFrame(runs, noteFrame(3, 'Found two.', at: '2026-10-23T20:15:11Z'));
      final run = runs['t1']!.single.finished('2026-10-23T20:15:11Z');
      expect(doneWords(run), 'Worked for 11 s · 1 step');
      final thought = applyRunFrame(const {}, noteFrame(1, 'Thinking it over.'))['t1']!.single.finished();
      expect(doneWords(thought), startsWith('Thought for'));
    });
  });

  test('durations read in minutes past a minute', () {
    expect(durationWords(const Duration(seconds: 125)), '2 min 5 s');
    expect(durationWords(const Duration(minutes: 3)), '3 min');
    expect(durationWords(Duration.zero), '1 s');
  });
}
