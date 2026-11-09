import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/common/widgets.dart';
import '../../board/documents/document_view.dart';
import '../../board/documents/documents_api.dart';
import '../../board/documents/documents_tab.dart' show kindIcon;
import '../../board/notes/note_editor.dart';
import '../../board/notes/notes_api.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../tasks/work_projects.dart';
import '../workspace_state.dart';
import 'note_tree.dart';

/// Every note and document, in one tree with a folder per project.
final noteTreeProvider = FutureProvider.autoDispose<List<TreeFolder>>((ref) async {
  final results = await Future.wait([
    ref.watch(notesApiProvider).list(),
    ref.watch(documentsApiProvider).list(),
  ]);
  final projects = await ref.watch(workProjectsProvider.future);
  return buildNoteTree(projects, results[0], results[1]);
});

/// The Notes view: folders (projects, then No project) with their file
/// counts, opened and closed in place; a row opens the note or document.
class NotesView extends ConsumerStatefulWidget {
  const NotesView({super.key});

  @override
  ConsumerState<NotesView> createState() => _NotesViewState();
}

class _NotesViewState extends ConsumerState<NotesView> {
  Set<String> _open = const {};

  void _toggle(String key) => setState(() => _open = _open.contains(key)
      ? (_open.difference({key}))
      : {..._open, key});

  Future<void> _openFile(TreeFile f) async {
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => f.isNote
          ? NoteEditorScreen(noteId: f.id)
          : DocumentViewScreen(documentId: f.id, title: f.title, kind: f.kind),
    ));
    if (mounted) ref.invalidate(noteTreeProvider);
  }

  @override
  Widget build(BuildContext context) {
    final typed = ref.watch(workspaceQueryProvider);
    return ref.watch(noteTreeProvider).when(
          loading: () => const BoardNote('Loading…'),
          error: (e, _) => BoardNote(errorText(e), error: true),
          data: (tree) {
            final shown = filterTree(tree, typed);
            if (shown.isEmpty) return const BoardNote('No note matches that.');
            return RefreshIndicator(
              onRefresh: () async => ref.invalidate(noteTreeProvider),
              child: ListView(children: [
                for (final f in shown) ...[
                  _folderRow(f, typed.isNotEmpty || _open.contains(_key(f))),
                  if (typed.isNotEmpty || _open.contains(_key(f)))
                    for (final file in f.files) _fileRow(file),
                ],
              ]),
            );
          },
        );
  }

  String _key(TreeFolder f) => f.id ?? noProject;

  Widget _folderRow(TreeFolder f, bool open) {
    final n = f.files.length;
    return ListTile(
      key: Key('folder-${_key(f)}'),
      leading: Icon(open ? Icons.expand_more : Icons.chevron_right,
          color: Tokens.textSecondary),
      minLeadingWidth: Tokens.space5,
      title: Text(f.name,
          style: const TextStyle(fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
      trailing: Text(n == 1 ? '1 file' : '$n files',
          style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
      onTap: () => _toggle(_key(f)),
    );
  }

  Widget _fileRow(TreeFile f) => ListTile(
        key: Key('file-${f.id}'),
        contentPadding: const EdgeInsets.only(left: Tokens.space8 + Tokens.space4),
        leading: Icon(f.isNote ? Icons.sticky_note_2_outlined : kindIcon(f.kind),
            size: 20, color: Tokens.textSecondary),
        minLeadingWidth: Tokens.space5,
        title: Text(f.title.isEmpty ? 'Untitled' : f.title,
            maxLines: 1, overflow: TextOverflow.ellipsis),
        onTap: () => _openFile(f),
      );
}

/// The folder+ in the top-right: pick a folder, then write a new note there.
class NewNoteButton extends ConsumerWidget {
  const NewNoteButton({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final projects = chipProjects(await ref.read(workProjectsProvider.future));
    if (!context.mounted) return;
    final picked = await showModalBottomSheet<({String? id})>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (c) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: Tokens.space4),
            child: Text('New note in…',
                style: TextStyle(fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
          ),
          for (final p in projects)
            ListTile(
              leading: Icon(Icons.folder_outlined, color: AccentColors.of(c).strong),
              title: Text(p.name),
              onTap: () => Navigator.pop(c, (id: p.id)),
            ),
          ListTile(
            key: const Key('new-note-none'),
            leading: const Icon(Icons.folder_outlined),
            title: const Text(noProjectFolder),
            onTap: () => Navigator.pop(c, (id: null)),
          ),
        ]),
      ),
    );
    if (picked == null || !context.mounted) return;
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => NoteEditorScreen(projectId: picked.id),
    ));
    ref.invalidate(noteTreeProvider);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) => IconButton(
        key: const Key('new-note'),
        tooltip: 'New note',
        icon: const Icon(Icons.create_new_folder_outlined),
        onPressed: () => _create(context, ref),
      );
}
