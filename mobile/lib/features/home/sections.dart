import '../../api/models.dart';

class ChatSection {
  const ChatSection(this.label, this.rows);

  final String? label;
  final List<ChatRow> rows;
}

/// The main bot first, then pinned bots in the order they were pinned
/// (port of `avatarRow` in web/src/lib/sidebar.ts).
List<Bot> avatarRow(Iterable<Bot> bots) {
  final all = bots.toList();
  final pins = all.where((b) => !b.isPrimary && b.pinned).toList()
    ..sort((a, b) => (a.pinnedAt ?? '').compareTo(b.pinnedAt ?? ''));
  return [...all.where((b) => b.isPrimary), ...pins];
}

String plainText(String s) => s
    .replaceAll(RegExp(r'[*_`#>]'), '')
    .replaceAllMapped(RegExp(r'\[([^\]]*)\]\([^)]*\)'), (m) => m[1] ?? '')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();

/// Chats under group headings (port of `chatSections`): searching looks at
/// every chat; otherwise bots in the avatar row are left out of the list.
List<ChatSection> chatSections(
  List<ChatRow> rows,
  Map<String, Bot> bots,
  String query,
) {
  final wanted = query.trim().toLowerCase();
  final searching = wanted.isNotEmpty;
  bool pinned(ChatRow r) =>
      r.isBot && bots[r.id] != null && (bots[r.id]!.pinned || bots[r.id]!.isPrimary);
  final named = [
    for (final r in rows)
      if (searching || !pinned(r))
        r.isBot && bots[r.id] != null ? r.withName(bots[r.id]!.name) : r,
  ];
  final shown = searching
      ? named
          .where((r) =>
              r.name.toLowerCase().contains(wanted) ||
              plainText(r.preview ?? '').toLowerCase().contains(wanted))
          .toList()
      : named;
  String? label(ChatRow r) {
    if (!r.isBot) return null;
    final g = bots[r.id]?.group;
    return (g == null || g.isEmpty) ? null : g;
  }

  final ungrouped = [for (final r in shown) if (label(r) == null) r];
  final labels = {
    for (final r in shown)
      if (label(r) != null) label(r)!,
  }.toList()
    ..sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));
  return [
    if (ungrouped.isNotEmpty) ChatSection(null, ungrouped),
    for (final l in labels)
      ChatSection(l, [for (final r in shown) if (label(r) == l) r]),
  ];
}

/// What a chat row shows under the name, in words.
String previewLine(ChatRow row) {
  final text = plainText(row.preview ?? '');
  if (text.isEmpty) return '';
  if (row.previewKind != null && row.previewKind != 'text') return text;
  return row.fromYou ? 'You: $text' : text;
}
