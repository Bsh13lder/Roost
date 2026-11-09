import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../api/providers.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'avatar_editor.dart';
import 'picture_row.dart';
import 'bot_detail.dart';

Future<void> showEditBotSheet(BuildContext context, BotDetail bot) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => EditBotSheet(bot: bot),
  );
}

/// Name, job, group label and the avatar. One Save sends them together.
class EditBotSheet extends ConsumerStatefulWidget {
  const EditBotSheet({super.key, required this.bot});

  final BotDetail bot;

  @override
  ConsumerState<EditBotSheet> createState() => _EditBotSheetState();
}

class _EditBotSheetState extends ConsumerState<EditBotSheet> {
  late final _name = TextEditingController(text: widget.bot.name);
  late final _job = TextEditingController(text: widget.bot.job);
  late final _group = TextEditingController(text: widget.bot.group);
  late Avatar _avatar = widget.bot.avatar;
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _job.dispose();
    _group.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_name.text.trim().isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Give the bot a name.')));
      return;
    }
    setState(() => _busy = true);
    final id = widget.bot.id;
    final ok = await attempt(context, () async {
      final saved = await ref.read(apiClientProvider).patch('/api/bots/$id', {
        'name': _name.text.trim(),
        'job': _job.text.trim(),
        'group': _group.text.trim(),
        'avatar': _avatar.toJson(),
      });
      ref.read(botDetailProvider(id).notifier).replace(saved);
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(Tokens.space4, Tokens.space4, Tokens.space4,
          MediaQuery.of(context).viewInsets.bottom + Tokens.space4),
      child: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Name')),
          const SizedBox(height: Tokens.space3),
          TextField(
              controller: _job,
              decoration: const InputDecoration(labelText: 'Job')),
          const SizedBox(height: Tokens.space3),
          TextField(
              controller: _group,
              decoration: const InputDecoration(
                  labelText: 'Group label', hintText: 'Optional')),
          const SizedBox(height: Tokens.space4),
          AvatarEditor(
            avatar: _avatar,
            star: widget.bot.isPrimary,
            onChanged: (a) => setState(() => _avatar = a),
          ),
          const SizedBox(height: Tokens.space3),
          PictureRow(botId: widget.bot.id, hasPicture: widget.bot.avatar.picture != null),
          const SizedBox(height: Tokens.space4),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: const Text('Save changes'),
          ),
        ]),
      ),
    );
  }
}
