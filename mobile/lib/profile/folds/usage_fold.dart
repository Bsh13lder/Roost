import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';
import '../../api/usage.dart';
import '../../theme/tokens.dart';
import '../../widgets/profile_kit.dart';

/// The tallest bar in the per-day row, and each bar's width.
const _barMaxHeight = Tokens.space8;
const _barWidth = Tokens.space3;
const _barMinHeight = Tokens.space1 / 2;

/// Usage: this bot's tokens today and over the last 7 days, with a bar a day.
class UsageFold extends ConsumerWidget {
  const UsageFold({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LoadView<BotUsage>(
      load: () => fetchBotUsage(ref.read(apiClientProvider), botId),
      builder: (context, usage, _) {
        if (usage.total.tokens == 0) return const Quiet('No tokens used yet.');
        final t = usage.total;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Today: ${compactTokens(usage.todayTotal.tokens)} tokens',
                style: const TextStyle(fontSize: Tokens.fsRow)),
            const SizedBox(height: Tokens.space1),
            Text('Last $usageWeekDays days: ${compactTokens(t.tokens)} tokens',
                style: const TextStyle(fontSize: Tokens.fsRow)),
            Quiet('in ${compactTokens(t.tokensIn)} · '
                'out ${compactTokens(t.tokensOut)}'),
            _Bars(days: usage.perDay),
          ],
        );
      },
    );
  }
}

class _Bars extends StatelessWidget {
  const _Bars({required this.days});

  final List<UsageDay> days;

  @override
  Widget build(BuildContext context) {
    final most = days.fold<int>(
        0, (m, d) => d.counts.tokens > m ? d.counts.tokens : m);
    final color = Theme.of(context).colorScheme.primary;
    return SizedBox(
      height: _barMaxHeight,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final d in days)
            Padding(
              padding: const EdgeInsets.only(right: Tokens.space1),
              child: Semantics(
                label: '${d.day}: ${compactTokens(d.counts.tokens)} tokens',
                excludeSemantics: true,
                child: Container(
                  key: const Key('usage-bar'),
                  width: _barWidth,
                  height: most == 0
                      ? _barMinHeight
                      : (_barMaxHeight * d.counts.tokens / most)
                          .clamp(_barMinHeight, _barMaxHeight),
                  decoration: BoxDecoration(
                    color: d.counts.tokens == 0 ? Tokens.border : color,
                    borderRadius: BorderRadius.circular(Tokens.space1 / 2),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
