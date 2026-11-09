import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../app_version.dart';
import '../theme/tokens.dart';
import '../widgets/grouped_card.dart';
import 'update_banner.dart' show percent;
import 'update_controller.dart';

/// Settings' version card: the version, and "Check for updates", which
/// turns into "Install 1.0.2" (the new version) when a newer build is published.
class UpdateCard extends ConsumerWidget {
  const UpdateCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(updateProvider);
    final release = s.available;
    final message = s.error ?? s.note;
    final notifier = ref.read(updateProvider.notifier);
    return GroupedCard(caption: message, children: [
      const CardBody(
        child: Text('Version $appVersion',
            style: TextStyle(color: Tokens.textSecondary)),
      ),
      NavRow(
        key: const Key('settings-update'),
        icon: Icons.system_update_outlined,
        label: release == null
            ? 'Check for updates'
            : 'Install ${release.version}',
        value: _value(s),
        onTap: release == null
            ? () => notifier.check()
            : (s.downloading ? null : () => notifier.install()),
      ),
    ]);
  }

  String _value(UpdateState s) {
    if (s.downloading) return percent(s.progress!);
    if (s.checking) return 'Checking…';
    if (s.available != null) return 'Update available';
    return s.upToDate ? 'Up to date' : '';
  }
}
