import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/tokens.dart';
import 'update_controller.dart';

String percent(double progress) => '${(progress * 100).round()}%';

/// Home's calm line when a newer build is published:
/// "Update available · 1.0.2 — Install", then the download's progress.
/// Draws nothing when there is no update.
class UpdateBanner extends ConsumerWidget {
  const UpdateBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(updateProvider);
    final release = s.available;
    if (release == null) return const SizedBox.shrink();
    final message = s.error ?? s.note;
    return Container(
      key: const Key('update-banner'),
      margin: const EdgeInsets.fromLTRB(
          Tokens.space4, Tokens.space2, Tokens.space4, Tokens.space2),
      padding: const EdgeInsets.fromLTRB(
          Tokens.space4, Tokens.space2, Tokens.space2, Tokens.space2),
      decoration: BoxDecoration(
        color: Tokens.raised,
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
        border: Border.all(color: Tokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.system_update_outlined,
                size: 20, color: Tokens.textSecondary),
            const SizedBox(width: Tokens.space3),
            Expanded(
              child: Text('Update available · ${release.version}',
                  style: const TextStyle(fontSize: Tokens.fsBody)),
            ),
            TextButton(
              key: const Key('update-install'),
              onPressed: s.downloading
                  ? null
                  : () => ref.read(updateProvider.notifier).install(),
              child: Text(s.downloading ? percent(s.progress!) : 'Install'),
            ),
          ]),
          if (s.downloading)
            Padding(
              padding: const EdgeInsets.only(
                  right: Tokens.space2, bottom: Tokens.space2),
              child: LinearProgressIndicator(
                  key: const Key('update-progress'), value: s.progress),
            ),
          if (message != null)
            Padding(
              padding: const EdgeInsets.only(
                  right: Tokens.space2, bottom: Tokens.space2),
              child: Text(message,
                  key: const Key('update-message'),
                  style: TextStyle(
                      fontSize: Tokens.fsLabel,
                      color: s.error != null
                          ? Tokens.dangerText
                          : Tokens.textSecondary)),
            ),
        ],
      ),
    );
  }
}
