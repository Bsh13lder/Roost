import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/widgets.dart';
import 'documents_api.dart';
import 'payload_text.dart';

/// A read-only view: a doc as text, a sheet as a simple grid, a PDF as a
/// pointer to the web (Editing and PDF viewing come later).
class DocumentViewScreen extends ConsumerWidget {
  const DocumentViewScreen({
    super.key,
    required this.documentId,
    required this.title,
    required this.kind,
  });

  final String documentId;
  final String title;
  final String kind;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      backgroundColor: Tokens.bg,
      appBar: AppBar(title: Text(title, overflow: TextOverflow.ellipsis)),
      body: kind == 'pdf'
          ? const BoardNote('Open on the web to read this PDF.')
          : FutureBuilder(
              future: ref.read(documentsApiProvider).get(documentId),
              builder: (context, snap) {
                if (snap.hasError) return BoardNote(errorText(snap.error!), error: true);
                if (!snap.hasData) return const BoardNote('Loading…');
                final payload = snap.data!['payload'] as Map<String, dynamic>?;
                return kind == 'sheet' ? _Grids(sheetGrids(payload)) : _Text(docText(payload));
              },
            ),
    );
  }
}

class _Text extends StatelessWidget {
  const _Text(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => text.isEmpty
      ? const BoardNote('This document is empty.')
      : SingleChildScrollView(
          padding: const EdgeInsets.all(Tokens.space4),
          child: SelectableText(text, style: const TextStyle(fontSize: Tokens.fsBody, height: 1.5)),
        );
}

class _Grids extends StatelessWidget {
  const _Grids(this.grids);

  final List<SheetGrid> grids;

  @override
  Widget build(BuildContext context) {
    if (grids.isEmpty) return const BoardNote('This sheet is empty.');
    return ListView(children: [
      for (final g in grids) ...[
        SectionTitle(g.name),
        if (g.rows.isEmpty)
          const BoardNote('Nothing in this sheet.')
        else
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
            child: Table(
              defaultColumnWidth: const IntrinsicColumnWidth(),
              border: TableBorder.all(color: Tokens.border),
              children: [
                for (final row in g.rows)
                  TableRow(children: [
                    for (final cell in row)
                      Padding(
                        padding: const EdgeInsets.all(Tokens.space2),
                        child: Text(cell, style: const TextStyle(fontSize: Tokens.fsLabel)),
                      ),
                  ]),
              ],
            ),
          ),
      ],
    ]);
  }
}
