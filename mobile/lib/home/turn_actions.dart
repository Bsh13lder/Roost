import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_client.dart';
import '../api/api_error.dart';
import '../api/providers.dart';
import '../theme/tokens.dart';
import 'my_turn.dart';

/// Owner, 2026-11-05: a card in My turn can be skipped, or swapped for a new
/// instruction, from Home with a long press (Open · Skip · Give new
/// instruction), with no need to find the card first.

typedef SkipCall = ({String path, Map<String, String>? body});

/// The route that closes [row]'s card as a No: an Ask card answers no (a
/// Review first card declines), a Stuck card gives up, a proposal or key
/// request declines, a question is dismissed. Null for a kind it doesn't know.
SkipCall? skipRequest(TurnRow row) {
  final id = Uri.encodeComponent(row.id);
  return switch (row.kind) {
    'approval' => (
        path: '/api/approvals/$id/answer',
        body: {'answer': row.cardKind == 'plan' ? 'decline' : 'no'}
      ),
    'stuck' => (path: '/api/stuck/$id/give-up', body: null),
    'routine_proposal' => (path: '/api/routine-proposals/$id/decline', body: null),
    'skill_proposal' => (path: '/api/skill-proposals/$id/decline', body: null),
    'key_request' => (path: '/api/connector-requests/$id/decline', body: null),
    'question' => (path: '/api/questions/$id/dismiss', body: null),
    _ => null,
  };
}

Future<void> skipTurn(ApiClient api, TurnRow row) async {
  final call = skipRequest(row);
  if (call == null) return;
  await api.post(call.path, call.body);
}

/// Skips the card, then sends [text] to the bot's own chat as your message.
Future<void> giveNewInstruction(ApiClient api, TurnRow row, String text) async {
  final words = text.trim();
  if (words.isEmpty) return;
  await skipTurn(api, row);
  final thread = await api.post('/api/bots/${Uri.encodeComponent(row.botId)}/chat') as Map;
  await api.post('/api/threads/${thread['id']}/messages', {'text': words});
}

/// The long-press sheet on a My turn row.
Future<void> showTurnActions(BuildContext context, WidgetRef ref, TurnRow row) async {
  final canSkip = skipRequest(row) != null;
  final api = ref.read(apiClientProvider);
  final messenger = ScaffoldMessenger.maybeOf(context);
  final choice = await showModalBottomSheet<String>(
    context: context,
    backgroundColor: Tokens.panel,
    builder: (sheet) => SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Padding(
          padding: const EdgeInsets.all(Tokens.space4),
          child: Text(row.text, maxLines: 2, overflow: TextOverflow.ellipsis),
        ),
        ListTile(
          key: const Key('turn-open'),
          leading: const Icon(Icons.open_in_new),
          title: const Text('Open'),
          onTap: () => Navigator.pop(sheet, 'open'),
        ),
        if (canSkip)
          ListTile(
            key: const Key('turn-skip'),
            leading: const Icon(Icons.close),
            title: const Text('Skip'),
            subtitle: const Text('Closes the card as a No'),
            onTap: () => Navigator.pop(sheet, 'skip'),
          ),
        if (canSkip)
          ListTile(
            key: const Key('turn-instead'),
            leading: const Icon(Icons.edit_outlined),
            title: const Text('Give new instruction'),
            subtitle: const Text('Skips this and tells the bot what to do instead'),
            onTap: () => Navigator.pop(sheet, 'instead'),
          ),
      ]),
    ),
  );
  if (!context.mounted || choice == null) return;
  if (choice == 'open') {
    context.push(row.to);
    return;
  }
  final words = choice == 'instead' ? await _askWords(context) : null;
  if (choice == 'instead' && (words == null || words.trim().isEmpty)) return;
  try {
    if (words != null) {
      await giveNewInstruction(api, row, words);
    } else {
      await skipTurn(api, row);
    }
  } on ApiException catch (e) {
    messenger?.showSnackBar(SnackBar(content: Text(e.message)));
  }
  ref.invalidate(myTurnProvider);
}

Future<String?> _askWords(BuildContext context) {
  final field = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (dialog) => AlertDialog(
      title: const Text('New instruction'),
      content: TextField(
        key: const Key('turn-instead-text'),
        controller: field,
        autofocus: true,
        minLines: 1,
        maxLines: 5,
        decoration: const InputDecoration(hintText: 'What should it do instead?'),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(dialog), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(dialog, field.text), child: const Text('Send')),
      ],
    ),
  ).whenComplete(field.dispose);
}
