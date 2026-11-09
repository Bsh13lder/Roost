import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../api/providers.dart';
import '../../theme/tokens.dart';
import 'card_base.dart';

const _efforts = {'low', 'medium', 'high', 'max'};

/// The main bot proposes a model change; nothing changes until Switch. Not
/// now hides the card here; once switched it folds to one line.
class ModelSuggestionCard extends ConsumerStatefulWidget {
  const ModelSuggestionCard(
      {super.key, required this.body, required this.tainted});
  final String body;
  final bool tainted;

  @override
  ConsumerState<ModelSuggestionCard> createState() => _ModelCardState();
}

class _ModelCardState extends ConsumerState<ModelSuggestionCard> {
  bool _switched = false;
  bool _hidden = false;
  bool _busy = false;
  String? _error;

  Future<void> _switch(Json d) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(apiClientProvider).put('/api/bots/${str(d['bot_id'])}/model',
          {'model': d['model'], 'effort': d['effort']});
      if (mounted) setState(() => _switched = true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = decodeBody(widget.body);
    final ok = d != null &&
        ['bot_id', 'bot', 'model', 'label', 'reason']
            .every((k) => d[k] is String) &&
        (d['effort'] == null || _efforts.contains(d['effort']));
    if (!ok) return QuietLine(widget.body);
    final bot = str(d['bot']);
    final label = str(d['label']);
    if (_switched) {
      final e = d['effort'];
      return QuietLine(
          'Switched $bot to $label${e == null ? '' : ' at $e effort'}');
    }
    if (_hidden) return const SizedBox.shrink();
    return CardFrame(
      title: 'Switch $bot to $label?',
      badges: [if (widget.tainted) 'This run read outside content.'],
      footer: [
        CardButton('Switch',
            primary: true, onPressed: _busy ? null : () => _switch(d)),
        CardButton('Not now', onPressed: () => setState(() => _hidden = true)),
      ],
      children: [
        Text(str(d['reason']),
            style: const TextStyle(color: Tokens.textSecondary)),
        if (_error != null) CardError(_error!),
      ],
    );
  }
}
