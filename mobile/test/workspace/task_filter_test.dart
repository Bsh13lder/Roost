import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';
import 'package:roost_mobile/workspace/tasks/task_filter.dart';
import 'package:roost_mobile/workspace/tasks/task_sections.dart';

TaskItem t(String id,
        {String bucket = 'none',
        String? due,
        String priority = 'medium',
        String? project,
        String status = 'todo'}) =>
    TaskItem(
      id: id,
      title: id,
      status: status,
      priority: priority,
      dueDate: due,
      dueBucket: bucket,
      projectId: project,
    );

final open = [
  t('late', bucket: 'overdue', due: '2026-10-20', priority: 'urgent', project: 'p1'),
  t('now', bucket: 'today', due: '2026-10-22', priority: 'high', project: 'p1'),
  t('next', bucket: 'tomorrow', due: '2026-10-23T09:00:00+02:00'),
  t('week', bucket: 'week', due: '2026-10-27', priority: 'low', project: 'p2'),
  t('later', bucket: 'later', due: '2026-11-05'),
  t('loose', priority: 'high'),
];
final done = [t('old', status: 'done', bucket: 'today', due: '2026-10-22')];

List<String> ids(TaskFilter f, {String typed = ''}) =>
    [for (final x in applyFilter(f, open: open, done: done, typed: typed)) x.id];

void main() {
  group('filter', () {
    test('no chip on shows every open task, never the done ones', () {
      expect(const TaskFilter().isEmpty, isTrue);
      expect(ids(const TaskFilter()), ['late', 'now', 'next', 'week', 'later', 'loose']);
    });

    test('each date chip keeps its own tasks', () {
      const f = TaskFilter();
      expect(ids(f.toggleDate(DateFilter.today)), ['now']);
      expect(ids(f.toggleDate(DateFilter.overdue)), ['late']);
      expect(ids(f.toggleDate(DateFilter.upcoming)), ['next', 'week', 'later']);
      expect(ids(f.toggleDate(DateFilter.noDate)), ['loose']);
    });

    test('date chips combine as OR', () {
      final f = const TaskFilter()
          .toggleDate(DateFilter.today)
          .toggleDate(DateFilter.overdue);
      expect(ids(f), ['late', 'now']);
    });

    test('High priority keeps urgent and high, and narrows the dates', () {
      final high = const TaskFilter().toggleHigh();
      expect(ids(high), ['late', 'now', 'loose']);
      expect(ids(high.toggleDate(DateFilter.noDate)), ['loose']);
    });

    test('projects are OR among themselves and narrow the rest', () {
      final p1 = const TaskFilter().toggleProject('p1');
      expect(ids(p1), ['late', 'now']);
      expect(ids(p1.toggleProject('p2')), ['late', 'now', 'week']);
      expect(ids(p1.toggleDate(DateFilter.upcoming)), isEmpty);
      expect(ids(const TaskFilter().toggleProject(noProject)), ['next', 'later', 'loose']);
    });

    test('Done alone shows the done tasks; with a date chip both', () {
      final d = const TaskFilter().toggleDone();
      expect(ids(d), ['old']);
      expect(ids(d.toggleDate(DateFilter.today)), ['now', 'old']);
    });

    test('a second tap turns a chip off; clear turns all off', () {
      final f = const TaskFilter().toggleDate(DateFilter.today).toggleHigh();
      expect(f.toggleDate(DateFilter.today).toggleHigh().isEmpty, isTrue);
      expect(f.activeCount, 2);
      expect(f == const TaskFilter(), isFalse);
      expect(const TaskFilter().toggleHigh(), const TaskFilter().toggleHigh());
    });

    test('the typed words narrow too', () {
      expect(ids(const TaskFilter(), typed: 'LO'), ['loose']);
    });

    test('kept as JSON on the phone; anything odd reads as no filter', () {
      final f = const TaskFilter()
          .toggleDate(DateFilter.overdue)
          .toggleHigh()
          .toggleDone()
          .toggleProject('p1');
      expect(TaskFilter.fromJson(f.toJson()), f);
      expect(TaskFilter.fromJson('nonsense'), const TaskFilter());
      expect(TaskFilter.fromJson({'dates': ['bogus', 'today'], 'high': 'yes'}),
          const TaskFilter().toggleDate(DateFilter.today));
    });

    test('chip counts come from the open tasks', () {
      expect(countFor(DateFilter.overdue, open), 1);
      expect(countFor(DateFilter.upcoming, open), 3);
      expect(highCount(open), 3);
    });
  });

  group('sections', () {
    test('Overdue, Today, Tomorrow, each later day, No date, then Done', () {
      final s = sectionsOf([...open, ...done]);
      expect(s.map((x) => x.key),
          ['overdue', 'today', 'tomorrow', '2026-10-27', '2026-11-05', 'none', 'done']);
      expect(s.map((x) => x.title),
          ['Overdue', 'Today', 'Tomorrow', 'Tue 27 Oct', 'Thu 5 Nov', 'No date', 'Done']);
      expect(s.first.tone, SectionTone.late);
      expect(s.last.tone, SectionTone.done);
      expect(s.first.tasks.single.id, 'late');
    });

    test('later days come in date order whatever the input order', () {
      final s = sectionsOf([open[4], open[3]]);
      expect(s.map((x) => x.key), ['2026-10-27', '2026-11-05']);
    });

    test('nothing in, nothing out', () {
      expect(sectionsOf(const []), isEmpty);
    });
  });
}
