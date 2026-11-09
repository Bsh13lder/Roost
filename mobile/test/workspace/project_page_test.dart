import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/money/expense_line.dart';
import 'package:roost_mobile/board/projects/project_page.dart';
import 'package:roost_mobile/workspace/workspace_screen.dart';

import 'workspace_fakes.dart';

void main() {
  testWidgets('a project pill opens the project page', (tester) async {
    final calls = <String>[];
    await pumpWorkspace(tester, const WorkspaceScreen(), calls);
    await tester.tap(find.byKey(const Key('pill-t1')));
    await tester.pumpAndSettle();
    expect(find.byType(ProjectPage), findsOneWidget);
    expect(calls, contains('GET /api/projects/p1'));
  });

  testWidgets('the project page: stats, its tasks as rows, then its money',
      (tester) async {
    final calls = <String>[];
    await pumpWorkspace(tester, const ProjectPage(projectId: 'p1'), calls);
    expect(find.text('Club'), findsWidgets);
    expect(find.text('TOTAL BUDGET'), findsOneWidget);
    expect(calls, contains('GET /api/tasks?project_id=p1'));
    expect(find.byKey(const Key('check-t1')), findsOneWidget);
    // The same Todoist-style row as Tasks, swipe to finish included.
    expect(find.byKey(const Key('todo-t1')), findsOneWidget);

    await tester.scrollUntilVisible(find.text('Ticket sales'), 200);
    expect(find.text('Paint'), findsOneWidget);
    expect(find.text('+€30.00'), findsOneWidget);
    expect(find.byKey(const Key('money-topups')), findsOneWidget);

    await tester.tap(find.byKey(const Key('add-expense')));
    await tester.pumpAndSettle();
    final line = tester.widget<ExpenseLine>(find.byType(ExpenseLine));
    expect(line.projectId, 'p1');
  });
}
