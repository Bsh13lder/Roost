import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/kanban_groups.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';

TaskItem task(String id,
        {String status = 'todo',
        String bucket = 'none',
        String? due,
        String? project}) =>
    TaskItem(
        id: id,
        title: id,
        status: status,
        priority: 'medium',
        dueDate: due,
        dueBucket: bucket,
        projectId: project);

void main() {
  test('a card moves by the grouped field and a finished card is reopened', () {
    final finished = task('a', status: 'done');
    expect(moveFor(KanbanGroup.status, 'done', task('b')), isA<CompleteMove>());
    final m = moveFor(KanbanGroup.status, 'in_progress', finished);
    expect(m, isA<ReopenMove>());
    expect((m as ReopenMove).then, {'status': 'in_progress'});
    expect(moveFor(KanbanGroup.project, 'none', task('c')),
        isA<PatchMove>().having((p) => p.patch, 'patch', {'project_id': null}));
    expect(moveFor(KanbanGroup.due, 'overdue', task('d')), isA<NoMove>());
    expect(moveFor(KanbanGroup.due, 'week', task('d')), isA<PickDayMove>());
  });

  test('columns sort tasks by status, due bucket and project', () {
    expect(columnOf(task('a', status: 'in_progress'), KanbanGroup.status),
        'in_progress');
    expect(columnOf(task('a', bucket: 'today'), KanbanGroup.due), 'today');
    expect(columnOf(task('a', project: 'p1'), KanbanGroup.project), 'p1');
  });
}
