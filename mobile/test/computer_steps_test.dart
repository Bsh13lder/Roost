import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/features/chat/computer_steps.dart';

Map<String, dynamic> step(
  int n, {
  String run = 'r1',
  String bot = 'b1',
  String thread = 't1',
  String kind = 'click',
  String line = 'Clicked Messages',
  String? host = 'www.upwork.com',
  String at = '2026-10-23T12:00:00Z',
}) => {
  'type': 'computer_step',
  'bot_id': bot,
  'thread_id': thread,
  'run_id': run,
  'step': n,
  'kind': kind,
  'line': line,
  'host': host,
  'at': at,
};

Map<String, Object?> msg(String id, String role, String at) => {
  'id': id,
  'thread_id': 't1',
  'role': role,
  'body': id,
  'tainted': false,
  'seq': 1,
  'created_at': at,
  'kind': 'text',
};

void main() {
  group('applyComputerFrame', () {
    test('a step starts a run for its thread, in step order', () {
      var runs = applyComputerFrame(const {}, step(2, line: 'Second'));
      runs = applyComputerFrame(runs, step(1, kind: 'look', line: 'First'));
      final run = runs['t1']!.single;
      expect(run.runId, 'r1');
      expect(run.botId, 'b1');
      expect(run.done, isFalse);
      expect([for (final s in run.steps) s.line], ['First', 'Second']);
      expect(run.current.line, 'Second');
      expect(run.host, 'www.upwork.com');
    });

    test('the same step number again replaces it', () {
      var runs = applyComputerFrame(const {}, step(1, line: 'Old'));
      runs = applyComputerFrame(runs, step(1, line: 'New'));
      expect(runs['t1']!.single.steps.single.line, 'New');
    });

    test('a new run of the same bot ends its earlier one', () {
      var runs = applyComputerFrame(const {}, step(1));
      runs = applyComputerFrame(runs, step(1, run: 'r2'));
      expect([for (final r in runs['t1']!) r.done], [true, false]);
    });

    test('the bot leaving On it ends its runs; On it again does not', () {
      var runs = applyComputerFrame(const {}, step(1));
      runs = applyComputerFrame(runs, {
        'type': 'bot_status',
        'bot_id': 'b1',
        'status': 'on_it',
      });
      expect(runs['t1']!.single.done, isFalse);
      runs = applyComputerFrame(runs, {
        'type': 'bot_status',
        'bot_id': 'b1',
        'status': 'resting',
      });
      expect(runs['t1']!.single.done, isTrue);
    });

    test('the host is the latest step that named one', () {
      var runs = applyComputerFrame(const {}, step(1, host: 'a.com'));
      runs = applyComputerFrame(runs, step(2, host: null, kind: 'open_app'));
      expect(runs['t1']!.single.host, 'a.com');
    });

    test('a bad frame changes nothing', () {
      final runs = applyComputerFrame(const {}, step(1));
      for (final bad in [
        {'type': 'computer_step', 'bot_id': 'b1'},
        {...step(2), 'step': 'two'},
        {...step(2), 'line': null},
        {'type': 'something_else'},
      ]) {
        expect(applyComputerFrame(runs, bad), same(runs));
      }
    });

    test('a removed bot loses its runs', () {
      final runs = applyComputerFrame(const {}, step(1));
      final next = applyComputerFrame(runs, {
        'type': 'bot_removed',
        'bot_id': 'b1',
      });
      expect(next['t1'] ?? const [], isEmpty);
    });

    test('the snapshot seeds the running steps; missing field means none', () {
      final runs = applyComputerFrame(const {}, {
        'type': 'snapshot',
        'bots': [
          {
            'id': 'b1',
            'status': 'on_it',
            'computer_steps': [step(1), step(2, line: 'Typing')],
          },
          {'id': 'b2', 'status': 'resting'},
        ],
      });
      final run = runs['t1']!.single;
      expect(run.steps.length, 2);
      expect(run.done, isFalse);
      expect(
        applyComputerFrame(const {}, {'type': 'snapshot', 'bots': []}),
        isEmpty,
      );
    });

    test('the server snapshot\'s top-level computer_steps seed the run', () {
      final runs = applyComputerFrame(const {}, {
        'type': 'snapshot',
        'bots': [
          {'id': 'b1', 'status': 'on_it'},
        ],
        'computer_steps': {
          'b1': [step(1), step(2)],
        },
      });
      final run = runs['t1']!.single;
      expect(run.steps.length, 2);
      expect(run.done, isFalse);
    });

    test('the snapshot\'s kept runs come back finished, after a restart', () {
      final runs = applyComputerFrame(const {}, {
        'type': 'snapshot',
        'bots': [
          {'id': 'b1', 'status': 'on_it'},
          {'id': 'b2', 'status': 'resting'},
        ],
        'computer_kept': {
          'b1': [
            [step(1, run: 'r0', thread: 't2', at: '2026-10-23T11:00:00Z')],
            [step(1), step(2)],
          ],
          'b2': 'not a list',
        },
      });
      final run = runs['t1']!.single;
      expect(run.runId, 'r1');
      expect(run.count, 2);
      expect(run.done, isTrue); // on_it on something else: still a kept card
      expect(runs['t2']!.single.done, isTrue);
    });

    test('a kept run and the running one in the same chat', () {
      final runs = applyComputerFrame(const {}, {
        'type': 'snapshot',
        'bots': [
          {'id': 'b1', 'status': 'on_it'},
        ],
        'computer_kept': {
          'b1': [
            [step(1, run: 'r0', at: '2026-10-23T11:00:00Z')],
          ],
        },
        'computer_steps': {
          'b1': [step(1, run: 'r1')],
        },
      });
      final list = runs['t1']!;
      expect(list.map((r) => r.runId), ['r0', 'r1']);
      expect(list.map((r) => r.done), [true, false]);
    });

    test('steps per run are capped, keeping the newest', () {
      var runs = <String, List<ComputerRun>>{};
      for (var i = 1; i <= maxStepsPerRun + 5; i++) {
        runs = applyComputerFrame(runs, step(i, line: 'Step $i'));
      }
      final run = runs['t1']!.single;
      expect(run.steps.length, maxStepsPerRun);
      expect(run.current.line, 'Step ${maxStepsPerRun + 5}');
      expect(run.count, maxStepsPerRun + 5);
    });
  });

  group('withComputerRuns', () {
    final messages = [
      Message.fromJson(msg('u1', 'user', '2026-10-23T11:59:00Z')),
      Message.fromJson(msg('b1', 'bot', '2026-10-23T11:59:30Z')),
      Message.fromJson(msg('u2', 'user', '2026-10-23T12:05:00Z')),
    ];

    test('a run sits right after your message that started it', () {
      final runs = applyComputerFrame(
        const {},
        step(1, at: '2026-10-23T12:00:00Z'),
      )['t1']!;
      final items = withComputerRuns(messages, runs);
      expect(
        [for (final i in items) i is Message ? i.id : 'run'],
        ['u1', 'run', 'b1', 'u2'],
      );
    });

    test('a run before any message goes first; none leaves the list alone', () {
      final runs = applyComputerFrame(
        const {},
        step(1, at: '2026-10-23T10:00:00Z'),
      )['t1']!;
      expect(withComputerRuns(messages, runs).first, isA<ComputerRun>());
      expect(withComputerRuns(messages, const []), messages);
    });
  });

  test('the done line names the host and the steps', () {
    var runs = applyComputerFrame(const {}, step(1));
    runs = applyComputerFrame(runs, step(2));
    expect(
      doneLine(runs['t1']!.single),
      'Used its computer · upwork.com · 2 steps',
    );
    final one = applyComputerFrame(const {}, step(1, host: null))['t1']!.single;
    expect(doneLine(one), 'Used its computer · 1 step');
  });
}
