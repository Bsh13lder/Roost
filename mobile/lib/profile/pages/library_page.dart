import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/documents/document_view.dart';
import '../../theme/tokens.dart';
import '../../widgets/grouped_card.dart';
import '../../widgets/profile_kit.dart';
import '../format.dart';
import '../profile_values.dart';

/// The bot's Library: the documents it made and the links from its chat,
/// grouped Today · This week · Earlier.
class LibraryPage extends ConsumerWidget {
  const LibraryPage({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final library = ref.watch(libraryProvider(botId));
    return Scaffold(
      appBar: AppBar(backgroundColor: Tokens.bg, title: const Text('Library')),
      body: library.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(libraryProvider(botId)),
            child: Text('${describe(e)} Try again'),
          ),
        ),
        data: (items) {
          final groups = libraryGroups(items, DateTime.now());
          if (groups.isEmpty) {
            return const Center(child: Quiet('No documents or links yet.'));
          }
          return ListView(children: [
            for (final g in groups)
              GroupedCard(label: g.label, children: [
                for (final item in g.items) _ItemRow(item: item),
              ]),
            const SizedBox(height: Tokens.space8),
          ]);
        },
      ),
    );
  }
}

class _ItemRow extends StatelessWidget {
  const _ItemRow({required this.item});

  final LibraryItem item;

  bool get _isLink => item.kind == LibraryKind.link;

  void _open(BuildContext context) {
    if (_isLink) {
      Clipboard.setData(ClipboardData(text: item.url));
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Link copied')));
      return;
    }
    Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => DocumentViewScreen(
            documentId: item.id, title: item.title, kind: item.docKind)));
  }

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(_isLink ? Icons.link : Icons.description_outlined,
          color: Tokens.textSecondary),
      title: Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(item.detail,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: Tokens.textSecondary)),
      trailing: Text(appShort(item.createdAt),
          style: const TextStyle(
              fontSize: Tokens.fsCaption, color: Tokens.textFaint)),
      onTap: () => _open(context),
    );
  }
}
