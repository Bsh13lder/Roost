import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';
import '../../api/usage.dart';
import '../../theme/tokens.dart';

/// This week's usage over every bot; null while loading or when it failed.
final usageSummaryProvider =
    FutureProvider.autoDispose<UsageSummary>((ref) async {
  return fetchUsage(ref.watch(apiClientProvider));
});

/// Settings' one line: "Tokens today: N · this week: M · busiest: Scout".
/// Hidden while it loads and when the gateway can't answer.
class UsageLine extends ConsumerWidget {
  const UsageLine({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(usageSummaryProvider).valueOrNull;
    if (summary == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: Tokens.space4, vertical: Tokens.space2),
      child: Text(usageLine(summary),
          key: const Key('settings-usage-line'),
          style: const TextStyle(
              fontSize: Tokens.fsLabel, color: Tokens.textSecondary)),
    );
  }
}
