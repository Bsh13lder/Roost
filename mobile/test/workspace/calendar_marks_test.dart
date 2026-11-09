// The clean calendar (2026-10-26): what each day holds, as markers and as
// the day panel's three sections. Pure rules, no widgets.
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';
import 'package:roost_mobile/routines/occurrences.dart';
import 'package:roost_mobile/workspace/calendar/day_marks.dart';

TaskItem t(String id,
        {String? due,
        String status = 'todo',
        String? remind,
        List<String> pre = const [],
        String? bot}) =>
    TaskItem(
        id: id,
        title: id,
        status: status,
        priority: 'medium',
        dueDate: due,
        reminderAt: remind,
        preReminders: pre,
        createdByBot: bot);

Map<String, dynamic> occ(String id, String day, String time, {String bot = 'b2'}) => {
      'routine_id': id, 'routine_name': 'News $id', 'bot_id': bot, 'bot_name': 'Bot $bot',
      'at': '${day}T$time:00Z', 'day': day, 'time': time,
    };

DateTime d(int day) => DateTime.utc(2026, 10, day);

void main() {
  final today = d(23);

  group('reminderFires', () {
    test('the reminder and its advance ones, as Madrid days and clocks, in order', () {
      final fires = reminderFires(t('a',
          remind: '2026-10-24T07:00:00+00:00',
          pre: ['2026-10-23T21:00:00+00:00', '-30m', 'nonsense', '-1d2h']));
      expect([for (final f in fires) '${f.day.day} ${f.clock}'],
          ['23 07:00', '23 23:00', '24 08:30', '24 09:00']);
    });

    test('none without a reminder, and none for a finished task', () {
      expect(reminderFires(t('a')), isEmpty);
      expect(reminderFires(t('a', remind: 'garbage')), isEmpty);
      expect(reminderFires(t('a', remind: '2026-10-24T07:00:00Z', status: 'done')), isEmpty);
      expect(reminderFires(t('a', remind: '2026-10-24T07:00:00Z', status: 'cancelled')), isEmpty);
    });

    test('a time with no zone is read as UTC, like the server stores it', () {
      expect(reminderFires(t('a', remind: '2026-10-24T07:00:00')).single.clock, '09:00');
    });
  });

  test('a task sits on its due day; an open late one sits on today', () {
    expect(placedDay(t('a', due: '2026-10-25'), today), d(25));
    expect(placedDay(t('a', due: '2026-10-20'), today), today);
    expect(placedDay(t('a', due: '2026-10-20', status: 'done'), today), d(20));
    expect(placedDay(t('a'), today), isNull);
    expect(isLate(t('a', due: '2026-10-20'), today), isTrue);
    expect(isLate(t('a', due: '2026-10-23'), today), isFalse);
  });

  test('day marks: tasks open first, reminder and routine counts, bots once', () {
    final marks = buildDayMarks(
      tasks: [
        t('done', due: '2026-10-25', status: 'done'),
        t('open', due: '2026-10-25T10:00:00+02:00', bot: 'b1'),
        t('late', due: '2026-10-19', bot: 'b1'),
        t('reminded', due: '2026-11-02', remind: '2026-10-25T08:00:00Z'),
      ],
      routines: groupRoutineDays([occ('r1', '2026-10-25', '09:00'), occ('r2', '2026-10-25', '18:00', bot: 'b1')]),
      today: today,
    );
    final sat = marks[d(25)]!;
    expect([for (final x in sat.tasks) x.id], ['open', 'done']);
    expect(sat.reminders, 1);
    expect(sat.routines, 2);
    expect(sat.botIds, ['b1', 'b2']);
    expect([for (final x in marks[today]!.tasks) x.id], ['late']);
    expect(marks[today]!.botIds, ['b1']);
    expect(marks.containsKey(d(19)), isFalse);
    expect(marks.containsKey(DateTime.utc(2026, 11, 2)), isTrue);
    expect(const DayMarks().isEmpty, isTrue);
  });

  test('the day plan: tasks by time with Late and All day, reminders, routines', () {
    final plan = dayPlan(
      today,
      [
        t('timed', due: '2026-10-23T18:30:00+02:00'),
        t('allday', due: '2026-10-23'),
        t('late', due: '2026-10-20'),
        t('finished', due: '2026-10-23T08:00:00+02:00', status: 'done'),
        t('ping', due: '2026-10-30', remind: '2026-10-23T07:00:00Z', pre: ['-30m', '2026-10-23T16:00:00Z']),
        t('elsewhere', due: '2026-10-24'),
      ],
      groupRoutineDays([occ('r1', '2026-10-23', '09:00'), occ('r1', '2026-10-23', '12:00')]),
      today,
    );
    expect([for (final r in plan.tasks) '${r.time} ${r.task.id}'],
        ['Late late', 'All day allday', '18:30 timed', '08:00 finished']);
    expect(plan.tasks.first.late, isTrue);
    expect([for (final r in plan.reminders) '${r.time} ${r.task.id}'], ['08:30 +2 ping']);
    expect(plan.routines.single.routineId, 'r1');
    expect(plan.isEmpty, isFalse);
    expect(dayPlan(d(28), const [], const {}, today).isEmpty, isTrue);
  });
}
