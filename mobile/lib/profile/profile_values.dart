import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../api/providers.dart';
import '../routines/routines_repo.dart';
import '../util/app_time.dart';

/// The caption under the profile's Notifications switch.
const notifyCaption = 'Get told when this bot finishes or is waiting for you.';

/// Days back that still count as "This week" in the Library.
const libraryWeekDays = 7;

/// The Computer row's word: On it while the bot works, Asleep when its
/// computer is not running, Idle otherwise; empty when the desk is unknown.
String computerStatusWord(BotStatus status, Map<String, dynamic>? desk) {
  if (status == BotStatus.onIt) return 'On it';
  if (desk == null) return '';
  final running = desk['computer'] == 'linux'
      ? desk['state'] == 'running'
      : desk['browser'] == 'running';
  return running ? 'Idle' : 'Asleep';
}

/// "2 on" for the Plan & routines row; empty when the bot has no routines.
String routinesOnLabel(List<Map<String, dynamic>> routines) {
  if (routines.isEmpty) return '';
  final on = routines.where((r) => r['enabled'] == true).length;
  return '$on on';
}

enum LibraryKind { document, link }

/// One thing in a bot's Library: a document it made or a link from its chat.
@immutable
class LibraryItem {
  const LibraryItem({
    required this.kind,
    required this.title,
    required this.detail,
    required this.createdAt,
    this.id = '',
    this.url = '',
    this.docKind = '',
  });

  final LibraryKind kind;
  final String title, detail, createdAt, id, url;

  /// A document's kind: doc, sheet or pdf.
  final String docKind;
}

typedef LibraryGroup = ({String label, List<LibraryItem> items});

String _bucket(LibraryItem item, DateTime today) {
  final DateTime day;
  try {
    day = appDay(parseServerTime(item.createdAt));
  } on FormatException {
    return 'Earlier';
  }
  final back = today.difference(day).inDays;
  if (back <= 0) return 'Today';
  return back < libraryWeekDays ? 'This week' : 'Earlier';
}

/// Newest first, then grouped Today · This week · Earlier by account-zone day.
List<LibraryGroup> libraryGroups(List<LibraryItem> items, DateTime now) {
  final today = appDay(now);
  final sorted = [...items]
    ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
  final groups = <LibraryGroup>[
    for (final label in const ['Today', 'This week', 'Earlier'])
      (
        label: label,
        items: [
          for (final i in sorted)
            if (_bucket(i, today) == label) i
        ]
      ),
  ];
  return [for (final g in groups) if (g.items.isNotEmpty) g];
}

String _kindWord(Object? kind) => switch (kind) {
      'sheet' => 'Sheet',
      'pdf' => 'PDF',
      _ => 'Document',
    };

/// Joins `GET /made`'s documents and `GET /links` into Library items.
List<LibraryItem> libraryItemsFrom(Object? made, Object? links) => [
      if (made is Map)
        for (final d in (made['documents'] as List? ?? const []))
          if (d is Map)
            LibraryItem(
              kind: LibraryKind.document,
              id: '${d['id'] ?? ''}',
              docKind: '${d['kind'] ?? ''}',
              title: '${d['title'] ?? ''}',
              detail: _kindWord(d['kind']),
              createdAt: '${d['created_at'] ?? ''}',
            ),
      if (links is List)
        for (final l in links)
          if (l is Map)
            LibraryItem(
              kind: LibraryKind.link,
              url: '${l['url'] ?? ''}',
              title: '${l['host'] ?? l['url'] ?? ''}',
              detail: '${l['url'] ?? ''}',
              createdAt: '${l['created_at'] ?? ''}',
            ),
    ];

/// The bot's routines, for the row's count and the Plan & routines page.
final botRoutinesProvider = FutureProvider.autoDispose
    .family<List<Map<String, dynamic>>, String>(
        (ref, botId) => ref.watch(routinesRepoProvider).forBot(botId));

/// The bot's desk (`GET /api/bots/{id}/desk`); null when it can't be read.
final deskProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, String>((ref, botId) async {
  try {
    final data = await ref
        .watch(apiClientProvider)
        .get('/api/bots/${Uri.encodeComponent(botId)}/desk');
    return data is Map ? data.cast<String, dynamic>() : null;
  } catch (_) {
    return null; // a desk that can't answer (503): the row shows no word
  }
});

/// The bot's documents and links, in one list.
final libraryProvider = FutureProvider.autoDispose
    .family<List<LibraryItem>, String>((ref, botId) async {
  final api = ref.watch(apiClientProvider);
  final id = Uri.encodeComponent(botId);
  final made = await api.get('/api/bots/$id/made');
  final links = await api.get('/api/bots/$id/links');
  return libraryItemsFrom(made, links);
});
