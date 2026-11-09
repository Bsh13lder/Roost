import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';
import 'package:roost_mobile/workspace/calendar/month_grid.dart';
import 'package:roost_mobile/workspace/notes/note_tree.dart';
import 'package:roost_mobile/workspace/tasks/work_projects.dart';
import 'package:roost_mobile/workspace/workspace_state.dart';

TaskItem task(String id, {String? due, String status = 'todo'}) => TaskItem(
    id: id, title: id, status: status, priority: 'medium', dueDate: due);

void main() {
  group('projects', () {
    test('projects: pinned first, archived left out of the chips', () {
      final list = chipProjects([
        const ProjectInfo(id: 'a', name: 'A'),
        const ProjectInfo(id: 'b', name: 'B', pinned: true),
        const ProjectInfo(id: 'c', name: 'C', archived: true),
      ]);
      expect(list.map((p) => p.id), ['b', 'a']);
      final p = ProjectInfo.fromJson({
        'id': 'x',
        'name': 'X',
        'color': '#ff0000',
        'pinned': true,
        'status': 'archived',
      });
      expect(p.color, '#ff0000');
      expect(p.pinned, isTrue);
      expect(p.archived, isTrue);
    });
  });

  test('the typed text matches titles, any case, any order of words', () {
    expect(matchesQuery('Pay the rent', ''), isTrue);
    expect(matchesQuery('Pay the rent', 'RENT pay'), isTrue);
    expect(matchesQuery('Pay the rent', 'milk'), isFalse);
  });

  group('calendar', () {
    test('the month grid starts on Monday and holds whole weeks', () {
      final days = monthGrid('2026-10');
      expect(days.first, DateTime.utc(2026, 9, 28));
      expect(days.length % 7, 0);
      expect(days.last, DateTime.utc(2026, 11, 1));
      expect(monthGrid('2026-02').first.weekday, DateTime.monday);
    });
  });

  test('the notes tree: a folder per project, No project last, counts', () {
    final tree = buildNoteTree(
      const [
        ProjectInfo(id: 'p1', name: 'Club'),
        ProjectInfo(id: 'p2', name: 'Home', pinned: true),
      ],
      [
        {'id': 'n1', 'title': 'Upgrades', 'project_id': 'p1'},
        {'id': 'n2', 'title': 'Loose', 'project_id': null},
      ],
      [
        {'id': 'd1', 'title': 'Numbers', 'kind': 'sheet', 'project_id': 'p1'},
      ],
    );
    expect(tree.map((f) => f.name), ['Home', 'Club', 'No project']);
    final club = tree[1];
    expect(club.files.map((f) => f.title), ['Numbers', 'Upgrades']);
    expect(club.files.first.kind, 'sheet');
    expect(club.files.last.isNote, isTrue);
    expect(tree.last.files.single.id, 'n2');
    expect(tree.first.files, isEmpty);
    expect(filterTree(tree, 'numb').single.files.single.id, 'd1');
  });
}
