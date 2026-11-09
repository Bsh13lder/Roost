import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/account_zone.dart';
import '../../api/models.dart';
import '../../api/providers.dart';
import '../../live/live_connection.dart';

/// The signed-in user's name, for the initials button.
final usernameProvider = FutureProvider<String>((ref) async {
  final me = await ref.watch(meProvider.future);
  return me['username'] as String? ?? '';
});

/// Loads the bots once over REST (Home shows before the socket's snapshot);
/// after that the live socket keeps [liveProvider] current.
final botsLoadProvider = FutureProvider<void>((ref) async {
  final data = await ref.watch(apiClientProvider).get('/api/bots');
  final bots = [
    for (final j in (data as List)) Bot.fromJson((j as Map).cast<String, dynamic>()),
  ];
  ref.read(liveProvider.notifier).seed(bots);
});

/// The chat list; reloads when a message frame arrives.
final chatsProvider = FutureProvider<List<ChatRow>>((ref) async {
  final sub = ref.read(frameBusProvider).stream
      .where((f) => f['type'] == 'message' || f['type'] == 'bot_removed')
      .listen((_) => ref.invalidateSelf());
  ref.onDispose(sub.cancel);
  final data = await ref.watch(apiClientProvider).get('/api/chats');
  return [
    for (final j in (data as List)) ChatRow.fromJson((j as Map).cast<String, dynamic>()),
  ];
});

String initialsOf(String name) {
  final parts = name.trim().split(RegExp(r'[\s._-]+')).where((p) => p.isNotEmpty);
  final letters = parts.take(2).map((p) => p[0].toUpperCase()).join();
  return letters.isEmpty ? '?' : letters;
}
