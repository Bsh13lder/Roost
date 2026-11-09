import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../projects/project_page.dart';
import 'reschedule_sheet.dart';
import 'task_actions.dart';
import 'task_models.dart';
import 'task_repo.dart';

Color priorityColor(String p) => switch (p) {
      'urgent' => Tokens.danger,
      'high' => Tokens.warn,
      'low' => Tokens.off,
      _ => Colors.transparent,
    };

/// Opens a project's page (its tasks and money).
Future<void> openProjectPage(BuildContext context, String projectId) =>
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => ProjectPage(projectId: projectId),
    ));

/// The long-press sheet: Move to project, Reschedule, Delete (each with Undo).
Future<void> showTaskMenu(BuildContext context, WidgetRef ref, TaskItem t) async {
  final actions = TaskActions(context);
  final choice = await showModalBottomSheet<String>(
    context: context,
    showDragHandle: true,
    builder: (c) => SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        for (final (value, label, icon) in const [
          ('move', 'Move to project', Icons.drive_file_move_outline),
          ('reschedule', 'Reschedule', Icons.schedule),
          ('delete', 'Delete', Icons.delete_outline),
        ])
          ListTile(
            key: Key('menu-$value'),
            leading: Icon(icon),
            title: Text(label),
            onTap: () => Navigator.pop(c, value),
          ),
      ]),
    ),
  );
  if (choice == null || !context.mounted) return;
  switch (choice) {
    case 'move':
      final list = await ref.read(taskProjectsProvider.future);
      if (!context.mounted) return;
      final r = await pickProject(context, list);
      if (r != null) await actions.moveToProject(t, r.project);
    case 'reschedule':
      final c = await showRescheduleSheet(context);
      if (c != null) await actions.reschedule(t, c);
    case 'delete':
      await actions.delete(t);
  }
}
