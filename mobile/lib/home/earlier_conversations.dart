import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../api/providers.dart';
import '../features/chat/message_view.dart';
import '../profile/format.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';

typedef Json = Map<String, dynamic>;

/// The chat's ⋯ menu: Earlier conversations (every thread but the live one,
/// newest first). Opening one shows it read-only.
class EarlierConversations extends ConsumerWidget {
  const EarlierConversations(
      {super.key, required this.botId, required this.mainThreadId});

  final String botId;
  final String? mainThreadId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Earlier conversations')),
      body: LoadView<List<Json>>(
        load: () async {
          final data = await ref
              .read(apiClientProvider)
              .get('/api/bots/${Uri.encodeComponent(botId)}/threads') as List;
          return [
            for (final t in data.reversed)
              if ((t as Map)['id'] != mainThreadId) t.cast<String, dynamic>(),
          ];
        },
        builder: (context, threads, _) {
          if (threads.isEmpty) {
            return const Padding(
                padding: EdgeInsets.all(Tokens.space4),
                child: Quiet('No earlier conversations.'));
          }
          return ListView(children: [
            for (final t in threads)
              ListTile(
                title: Text(t['title'] as String? ?? 'Conversation'),
                subtitle: Text(appShort('${t['created_at'] ?? ''}')),
                onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                    builder: (_) => _ReadOnlyThread(
                        threadId: t['id'] as String,
                        title: t['title'] as String? ?? 'Conversation'))),
              ),
          ]);
        },
      ),
    );
  }
}

class _ReadOnlyThread extends ConsumerWidget {
  const _ReadOnlyThread({required this.threadId, required this.title});

  final String threadId, title;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: LoadView<List<Message>>(
        load: () async {
          final data = await ref.read(apiClientProvider).get(
              '/api/threads/${Uri.encodeComponent(threadId)}/messages') as List;
          return [
            for (final m in data) Message.fromJson((m as Map).cast<String, dynamic>()),
          ];
        },
        builder: (context, messages, _) => ListView(children: [
          for (final m in messages) MessageView(message: m, text: m.body),
          const Padding(
              padding: EdgeInsets.all(Tokens.space4),
              child: Quiet('This conversation is read-only.')),
        ]),
      ),
    );
  }
}

/// Find in Chat: the loaded messages that contain the words.
Future<void> showFindInChat(BuildContext context, List<Message> messages) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => _FindSheet(messages: messages),
  );
}

class _FindSheet extends StatefulWidget {
  const _FindSheet({required this.messages});

  final List<Message> messages;

  @override
  State<_FindSheet> createState() => _FindSheetState();
}

class _FindSheetState extends State<_FindSheet> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final q = _query.trim().toLowerCase();
    final hits = q.isEmpty
        ? const <Message>[]
        : [
            for (final m in widget.messages)
              if (m.kind == 'text' && m.body.toLowerCase().contains(q)) m,
          ];
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SizedBox(
        height: MediaQuery.of(context).size.height * 0.6,
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.all(Tokens.space3),
            child: TextField(
              key: const Key('find-field'),
              autofocus: true,
              decoration: const InputDecoration(
                  hintText: 'Find in Chat', prefixIcon: Icon(Icons.search)),
              onChanged: (v) => setState(() => _query = v),
            ),
          ),
          Expanded(
            child: hits.isEmpty
                ? Quiet(q.isEmpty ? '' : 'Nothing found.')
                : ListView(children: [
                    for (final m in hits)
                      ListTile(
                        dense: true,
                        title: Text(m.body,
                            maxLines: 3, overflow: TextOverflow.ellipsis),
                        subtitle: Text(appShort(m.createdAt)),
                      ),
                  ]),
          ),
        ]),
      ),
    );
  }
}
