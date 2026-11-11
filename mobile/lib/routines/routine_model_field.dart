import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../profile/model_picker.dart';

/// The value that means "Same as the bot" (a dropdown value is never null here).
const sameAsBot = 'same';

/// A routine's own model (owner, 2026-11-09): Same as the bot by default, or
/// one of the bot models. Two failed runs in a row on it go back to the bot's.
class RoutineModelField extends ConsumerWidget {
  const RoutineModelField({super.key, required this.value, required this.onChanged});

  final String? value; // a model id, or null for the bot's
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final choices = ref.watch(modelsProvider).maybeWhen(
          data: (m) => [for (final c in m.choices) if (!c.isNew) c],
          orElse: () => const <ModelChoice>[],
        );
    final current = value ?? sameAsBot;
    final known = current == sameAsBot || choices.any((c) => c.id == current);
    return DropdownButtonFormField<String>(
      key: const Key('routine-model'),
      initialValue: current,
      decoration: const InputDecoration(
        labelText: 'Model',
        helperText: "A cheaper model suits a simple check. Two failed runs in a row go back to the bot's.",
        helperMaxLines: 2,
      ),
      items: [
        const DropdownMenuItem(value: sameAsBot, child: Text('Same as the bot')),
        for (final c in choices) DropdownMenuItem(value: c.id, child: Text(c.label)),
        if (!known) DropdownMenuItem(value: current, child: Text(current)),
      ],
      onChanged: (picked) => onChanged(picked == null || picked == sameAsBot ? null : picked),
    );
  }
}
