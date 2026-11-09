import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/format.dart';
import '../common/widgets.dart';
import 'document_view.dart';
import 'documents_api.dart';

/// The Board's Documents tab: the list; a row opens a read-only view.
/// [projectId] narrows it to one project.
class DocumentsTab extends ConsumerStatefulWidget {
  const DocumentsTab({super.key, this.projectId});

  final String? projectId;

  @override
  ConsumerState<DocumentsTab> createState() => _DocumentsTabState();
}

class _DocumentsTabState extends ConsumerState<DocumentsTab> {
  late final Future<List<Json>> _docs =
      ref.read(documentsApiProvider).list(projectId: widget.projectId);

  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: _docs,
      builder: (context, snap) {
        if (snap.hasError) return BoardNote(errorText(snap.error!), error: true);
        if (!snap.hasData) return const BoardNote('Loading…');
        final docs = snap.data!;
        if (docs.isEmpty) return const BoardNote('No documents yet.');
        return ListView.separated(
          itemCount: docs.length,
          separatorBuilder: (_, _) => const Divider(height: 1, color: Tokens.border),
          itemBuilder: (_, i) => documentTile(context, docs[i]),
        );
      },
    );
  }
}

IconData kindIcon(String kind) => switch (kind) {
      'sheet' => Icons.grid_on_outlined,
      'pdf' => Icons.picture_as_pdf_outlined,
      _ => Icons.description_outlined,
    };

/// One document row (also used on a project page).
Widget documentTile(BuildContext context, Json d) {
  final kind = d['kind'] as String;
  return ListTile(
    leading: Icon(kindIcon(kind), color: Tokens.textSecondary),
    title: Text('${d['title']}', maxLines: 1, overflow: TextOverflow.ellipsis),
    subtitle: Text(
      [
        switch (kind) { 'sheet' => 'Sheet', 'pdf' => 'PDF', _ => 'Doc' },
        'updated ${shortDate(d['updated_at'] as String)}',
        if (d['tainted'] == true) 'from web content',
      ].join(' · '),
      style: const TextStyle(color: Tokens.textSecondary),
    ),
    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => DocumentViewScreen(documentId: d['id'] as String, title: '${d['title']}', kind: kind),
    )),
  );
}
