import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import '../theme/accent.dart';
import '../widgets/profile_kit.dart';
import 'bot_detail.dart';

class ModelChoice {
  const ModelChoice(this.id, this.label, {this.isNew = false});

  final String id, label;
  final bool isNew;
}

class ModelsOut {
  const ModelsOut(this.choices, this.efforts, this.defaultEffort);

  factory ModelsOut.fromJson(Map<String, dynamic> j) => ModelsOut(
        [
          for (final c in (j['choices'] as List? ?? const []))
            ModelChoice((c as Map)['id'] as String, c['label'] as String? ?? '',
                isNew: c['new'] == true),
        ],
        [for (final e in (j['efforts'] as List? ?? const [])) e as String],
        ((j['default_effort'] as Map?) ?? const {}).cast<String, String>(),
      );

  final List<ModelChoice> choices;
  final List<String> efforts;
  final Map<String, String> defaultEffort;
}

String effortLabel(String? level) => level == null || level.isEmpty
    ? 'Default'
    : level[0].toUpperCase() + level.substring(1);

final modelsProvider = FutureProvider<ModelsOut>((ref) async {
  final data = await ref.read(apiClientProvider).get('/api/models');
  return ModelsOut.fromJson((data as Map).cast<String, dynamic>());
});

/// The Model and Effort rows of a bot's Info. Picking either saves at once.
class ModelRows extends ConsumerWidget {
  const ModelRows({super.key, required this.bot});

  final BotDetail bot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final models = ref.watch(modelsProvider);
    return models.when(
      loading: () => const InfoRow(label: 'Model', value: '…'),
      error: (e, _) => InfoRow(
          label: 'Model',
          value: 'Try again',
          onTap: () => ref.invalidate(modelsProvider)),
      data: (m) => Column(children: [
        InfoRow(
          label: 'Model',
          value: bot.modelLabel,
          onTap: () => _pickModel(context, ref, m),
        ),
        InfoRow(
          label: 'Effort',
          value: bot.effort == null
              ? _defaultLabel(m)
              : effortLabel(bot.effort),
          onTap: () => _pickEffort(context, ref, m),
        ),
      ]),
    );
  }

  String _defaultLabel(ModelsOut m) {
    final level = m.defaultEffort[bot.model];
    return level == null ? 'Default' : 'Default ($level)';
  }

  Future<void> _pickModel(BuildContext context, WidgetRef ref, ModelsOut m) async {
    final id = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => ModelList(choices: m.choices, current: bot.model),
    );
    if (id == null || id == bot.model || !context.mounted) return;
    await _save(context, ref, id, bot.effort);
  }

  Future<void> _pickEffort(BuildContext context, WidgetRef ref, ModelsOut m) async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => EffortList(
          efforts: m.efforts,
          current: bot.effort,
          defaultLabel: _defaultLabel(m)),
    );
    if (picked == null || !context.mounted) return;
    await _save(context, ref, bot.model, picked == 'default' ? null : picked);
  }

  Future<void> _save(BuildContext context, WidgetRef ref, String model,
      String? effort) async {
    await attempt(context, () async {
      final saved = await ref
          .read(apiClientProvider)
          .put('/api/bots/${bot.id}/model', {'model': model, 'effort': effort});
      ref.read(botDetailProvider(bot.id).notifier).replace(saved);
    });
  }
}

/// The models the gateway offers, one row each; the current one is ticked.
class ModelList extends StatelessWidget {
  const ModelList({super.key, required this.choices, required this.current});

  final List<ModelChoice> choices;
  final String current;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        for (final c in choices)
          ListTile(
            title: Text(c.isNew ? '${c.label} · New' : c.label),
            trailing: c.id == current
                ? Icon(Icons.check, color: AccentColors.of(context).strong)
                : null,
            onTap: () => Navigator.pop(context, c.id),
          ),
      ]),
    );
  }
}

class EffortList extends StatelessWidget {
  const EffortList({
    super.key,
    required this.efforts,
    required this.current,
    required this.defaultLabel,
  });

  final List<String> efforts;
  final String? current;
  final String defaultLabel;

  @override
  Widget build(BuildContext context) {
    Widget row(String value, String label) => ListTile(
          title: Text(label),
          trailing: (current ?? 'default') == value
              ? Icon(Icons.check, color: AccentColors.of(context).strong)
              : null,
          onTap: () => Navigator.pop(context, value),
        );
    return SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        row('default', defaultLabel),
        for (final e in efforts) row(e, effortLabel(e)),
      ]),
    );
  }
}
