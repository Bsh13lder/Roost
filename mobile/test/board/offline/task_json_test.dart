import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';

void main() {
  test('TaskItem.toJson round-trips through fromJson and JSON text', () {
    final wire = {
      'id': 't1',
      'title': 'Pay rent',
      'status': 'todo',
      'priority': 'high',
      'description': 'by card',
      'due_date': '2026-11-09',
      'reminder_at': '2026-11-09T09:00:00+01:00',
      'pre_reminders': ['1d'],
      'project_id': 'p1',
      'tags': ['home'],
      'steps': [
        {'id': 's1', 'title': 'Find card', 'done': true},
      ],
      'starred': true,
      'due_bucket': 'tomorrow',
      'owner': 'user',
      'created_at': '2026-11-08T10:00:00Z',
      'updated_at': '2026-11-08T11:00:00Z',
      'completed_at': null,
      'tainted': true,
      'repeat_text': 'every month',
      'money': {'left': '12.00', 'currency': 'EUR', 'over': false},
      'comment_count': 2,
      'created_by_bot': 'b1',
    };
    final first = TaskItem.fromJson(wire);
    final text = jsonEncode(first.toJson());
    final back =
        TaskItem.fromJson((jsonDecode(text) as Map).cast<String, dynamic>());
    expect(back.toJson(), first.toJson());
    expect(back.title, 'Pay rent');
    expect(back.steps.single.done, isTrue);
    expect(back.money?.left, '12.00');
    expect(back.commentCount, 2);
    expect(back.createdByBot, 'b1');
    expect(back.dueBucket, 'tomorrow');
  });

  test('a bare task round-trips with its defaults', () {
    final t = TaskItem.fromJson({'id': 't2'});
    final back = TaskItem.fromJson(t.toJson());
    expect(back.toJson(), t.toJson());
    expect(back.money, isNull);
    expect(back.steps, isEmpty);
  });

  test('withStatus makes a new task and leaves the old one alone', () {
    final t = TaskItem.fromJson({'id': 't3', 'title': 'Milk'});
    final done = t.withStatus('done');
    expect(done.isDone, isTrue);
    expect(done.title, 'Milk');
    expect(t.isDone, isFalse);
  });
}
