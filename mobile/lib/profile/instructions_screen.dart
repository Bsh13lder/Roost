import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'bot_detail.dart';

/// Instructions are Markdown in sections (Who you are and context · What you
/// do · Rules · Tone · Team). Split on `## ` headings; text before the first
/// heading is kept as its own section.
List<(String, String)> splitSections(String text) {
  final sections = <(String, String)>[];
  String? title;
  final body = <String>[];
  void flush() {
    final joined = body.join('\n').trim();
    if (title != null || joined.isNotEmpty) {
      sections.add((title ?? 'Instructions', joined));
    }
    body.clear();
  }

  for (final line in text.split('\n')) {
    final m = RegExp(r'^##\s+(.+?)\s*$').firstMatch(line);
    if (m != null) {
      flush();
      title = m.group(1);
    } else {
      body.add(line);
    }
  }
  flush();
  return sections;
}

String joinSections(List<(String, String)> sections) => sections
    .where((s) => s.$2.trim().isNotEmpty)
    .map((s) => '## ${s.$1}\n\n${s.$2.trim()}')
    .join('\n\n');

class InstructionsScreen extends ConsumerStatefulWidget {
  const InstructionsScreen({super.key, required this.botId});

  final String botId;

  @override
  ConsumerState<InstructionsScreen> createState() => _InstructionsScreenState();
}

class _InstructionsScreenState extends ConsumerState<InstructionsScreen> {
  List<(String, TextEditingController)>? _fields;
  bool _busy = false;

  @override
  void dispose() {
    for (final f in _fields ?? const <(String, TextEditingController)>[]) {
      f.$2.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final text = joinSections([for (final f in _fields!) (f.$1, f.$2.text)]);
    setState(() => _busy = true);
    final ok = await attempt(context, () async {
      final saved = await ref
          .read(apiClientProvider)
          .patch('/api/bots/${widget.botId}', {'instructions': text});
      ref.read(botDetailProvider(widget.botId).notifier).replace(saved);
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final bot = ref.watch(botDetailProvider(widget.botId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Instructions'),
        backgroundColor: Tokens.bg,
        actions: [
          if (_fields != null)
            TextButton(onPressed: _busy ? null : _save, child: const Text('Save')),
        ],
      ),
      body: bot.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Quiet(describe(e), bad: true)),
        data: (b) {
          _fields ??= [
            for (final s in splitSections(b.instructions))
              (s.$1, TextEditingController(text: s.$2)),
            if (splitSections(b.instructions).isEmpty)
              ('What you do', TextEditingController()),
          ];
          return ListView(
            padding: const EdgeInsets.all(Tokens.space4),
            children: [
              for (final f in _fields!) ...[
                Text(f.$1,
                    style: const TextStyle(
                        fontSize: Tokens.fsLabel, color: Tokens.textSecondary)),
                const SizedBox(height: Tokens.space1),
                TextField(controller: f.$2, minLines: 2, maxLines: 12),
                const SizedBox(height: Tokens.space4),
              ],
            ],
          );
        },
      ),
    );
  }
}
