import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/widgets.dart';
import '../documents/documents_tab.dart';
import '../notes/note_editor.dart';
import '../tasks/task_repo.dart';
import '../../workspace/tasks/todo_row.dart';
import '../tasks/task_models.dart';
import 'project_edit.dart';
import 'project_money.dart';
import 'project_stats.dart';
import 'projects_api.dart';
import 'topups_sheet.dart';

/// A project's page at `/board/projects/:projectId`: the header card of three
/// stats, then its tasks (the Workspace's rows), its money (expenses, income,
/// Add expense and top-ups), notes and documents.
class ProjectPage extends ConsumerStatefulWidget {
  const ProjectPage({super.key, required this.projectId});

  final String projectId;

  @override
  ConsumerState<ProjectPage> createState() => _ProjectPageState();
}

class _ProjectPageState extends ConsumerState<ProjectPage> {
  late Future<Json> _project = ref.read(projectsApiProvider).get(widget.projectId);

  void _reload() {
    if (!mounted) return;
    setState(() => _project = ref.read(projectsApiProvider).get(widget.projectId));
  }

  void _push(Widget page) => Navigator.of(context)
      .push(MaterialPageRoute<void>(builder: (_) => page))
      .then((_) => _reload());

  Future<void> _sheet(Widget body) async {
    final changed = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => body,
    );
    if (changed == true) _reload();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Tokens.bg,
      appBar: AppBar(title: const Text('Project'), actions: [
        FutureBuilder(
          future: _project,
          builder: (context, snap) => snap.hasData
              ? Row(children: [
                  TextButton(
                      key: const Key('topups'),
                      onPressed: () => _sheet(TopupsSheet(project: snap.data!)),
                      child: const Text('Top-ups')),
                  TextButton(
                      key: const Key('edit-project'),
                      onPressed: () =>
                          _sheet(ProjectEditSheet(project: snap.data!)),
                      child: const Text('Edit')),
                ])
              : const SizedBox.shrink(),
        ),
      ]),
      body: FutureBuilder(
        future: _project,
        builder: (context, snap) {
          if (snap.hasError) return BoardNote(errorText(snap.error!), error: true);
          if (!snap.hasData) return const BoardNote('Loading…');
          return _page(snap.data!);
        },
      ),
    );
  }

  Widget _page(Json p) {
    final currency = p['currency'] as String;
    return ListView(children: [
      ProjectHeaderCard(project: p),
      _ProjectTasks(projectId: widget.projectId),
      ProjectMoney(project: p, onChanged: _reload),
      SectionTitle('Notes',
          trailing: TextButton(
            onPressed: () => _push(NoteEditorScreen(projectId: widget.projectId)),
            child: const Text('New note'),
          )),
      for (final n in (p['notes'] as List))
        ListTile(
          title: Text('${(n as Map)['title']}'),
          subtitle: Text('${n['snippet']}',
              maxLines: 1, overflow: TextOverflow.ellipsis),
          onTap: () => _push(NoteEditorScreen(noteId: n['id'] as String)),
        ),
      if ((p['notes'] as List).isEmpty) const BoardNote('No notes yet.'),
      const SectionTitle('Documents'),
      for (final d in (p['documents'] as List))
        documentTile(context, Map<String, dynamic>.from(d as Map)),
      if ((p['documents'] as List).isEmpty) const BoardNote('No documents yet.'),
      Padding(
        padding: const EdgeInsets.all(Tokens.space4),
        child: Text('Amounts in $currency, as the server reckons them.',
            style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
      ),
    ]);
  }
}

/// The project's open tasks, in the same Todoist-style rows as Tasks: a
/// finished row hides at once and comes back if the server refuses.
class _ProjectTasks extends ConsumerStatefulWidget {
  const _ProjectTasks({required this.projectId});

  final String projectId;

  @override
  ConsumerState<_ProjectTasks> createState() => _ProjectTasksState();
}

class _ProjectTasksState extends ConsumerState<_ProjectTasks> {
  Set<String> _hidden = const {};

  void _completing(TaskItem t, Future<bool> result) {
    setState(() => _hidden = {..._hidden, t.id});
    result.then((ok) {
      if (!ok && mounted) setState(() => _hidden = _hidden.difference({t.id}));
    });
  }

  @override
  Widget build(BuildContext context) {
    final query = 'project_id=${Uri.encodeQueryComponent(widget.projectId)}';
    final tasks = ref.watch(taskListProvider(query));
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SectionTitle('Tasks'),
      ...tasks.when(
        loading: () => const [BoardNote('Loading…')],
        error: (e, _) => [BoardNote(errorText(e), error: true)],
        data: (all) {
          final list = [for (final t in all) if (!_hidden.contains(t.id)) t];
          return list.isEmpty
              ? const [BoardNote('No open tasks.')]
              : [
                  for (final t in list)
                    TodoRow(
                      key: ValueKey('todo-${t.id}'),
                      task: t,
                      projects: const {},
                      onCompleting: _completing,
                    ),
                ];
        },
      ),
    ]);
  }
}
