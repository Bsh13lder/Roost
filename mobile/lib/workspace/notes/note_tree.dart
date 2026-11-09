import '../tasks/work_projects.dart';
import '../workspace_state.dart';

/// One file in the notes tree: a note, or a document (doc, sheet or pdf).
class TreeFile {
  const TreeFile({required this.id, required this.title, required this.kind});

  final String id;
  final String title;

  /// `note`, or a document's kind.
  final String kind;

  bool get isNote => kind == 'note';
}

/// A folder: one project, or "No project" (id null).
class TreeFolder {
  const TreeFolder({required this.id, required this.name, required this.files, this.color});

  final String? id;
  final String name;
  final String? color;
  final List<TreeFile> files;
}

const noProjectFolder = 'No project';

TreeFile _note(Map<String, dynamic> n) =>
    TreeFile(id: n['id'] as String, title: '${n['title'] ?? ''}', kind: 'note');

TreeFile _doc(Map<String, dynamic> d) => TreeFile(
    id: d['id'] as String, title: '${d['title'] ?? ''}', kind: '${d['kind'] ?? 'doc'}');

List<TreeFile> _sorted(Iterable<TreeFile> files) {
  final list = files.toList()
    ..sort((a, b) => a.title.toLowerCase().compareTo(b.title.toLowerCase()));
  return List.unmodifiable(list);
}

/// Folders = the projects (pinned first), then No project. A file whose
/// project is unknown (archived, gone) lands in No project.
List<TreeFolder> buildNoteTree(
  List<ProjectInfo> projects,
  List<Map<String, dynamic>> notes,
  List<Map<String, dynamic>> documents,
) {
  final ordered = [
    ...projects.where((p) => p.pinned),
    ...projects.where((p) => !p.pinned),
  ];
  final known = {for (final p in ordered) p.id};
  final files = [
    for (final n in notes) (n['project_id'] as String?, _note(n)),
    for (final d in documents) (d['project_id'] as String?, _doc(d)),
  ];
  List<TreeFile> inFolder(String? id) => _sorted(files
      .where((f) => id == null ? !known.contains(f.$1) : f.$1 == id)
      .map((f) => f.$2));
  return List.unmodifiable([
    for (final p in ordered)
      TreeFolder(id: p.id, name: p.name, color: p.color, files: inFolder(p.id)),
    TreeFolder(id: null, name: noProjectFolder, files: inFolder(null)),
  ]);
}

/// Only the files whose title matches [query], in folders that still hold one.
List<TreeFolder> filterTree(List<TreeFolder> tree, String query) {
  if (query.trim().isEmpty) return tree;
  return List.unmodifiable([
    for (final f in tree)
      if (f.files.any((x) => matchesQuery(x.title, query)))
        TreeFolder(
          id: f.id,
          name: f.name,
          color: f.color,
          files: List.unmodifiable(f.files.where((x) => matchesQuery(x.title, query))),
        ),
  ]);
}
