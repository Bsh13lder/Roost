import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/tokens.dart';
import 'calendar/calendar_view.dart';
import 'notes/notes_view.dart';
import 'tasks/tasks_header.dart';
import 'tasks/tasks_view.dart';
import 'workspace_bar.dart';
import 'workspace_state.dart';

/// The Workspace, opened from Home's grid button: Tasks, Notes or Calendar
/// above one fixed bottom bar.
class WorkspaceScreen extends ConsumerWidget {
  const WorkspaceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final section = ref.watch(workspaceSectionProvider);
    return Scaffold(
      backgroundColor: Tokens.bg,
      appBar: AppBar(
        toolbarHeight: 52,
        title: section == WorkspaceSection.tasks
            ? const TasksTitle()
            : Text(section.label,
                style: const TextStyle(
                    fontSize: Tokens.fsTitle, fontWeight: FontWeight.w700)),
        actions: [
          if (section == WorkspaceSection.notes) const NewNoteButton(),
          if (section == WorkspaceSection.tasks) const TasksActions(),
        ],
      ),
      body: Column(children: [
        Expanded(
          child: switch (section) {
            WorkspaceSection.tasks => const TasksView(),
            WorkspaceSection.notes => const NotesView(),
            WorkspaceSection.calendar => const WorkCalendarView(),
          },
        ),
        const WorkspaceBar(),
      ]),
    );
  }
}
