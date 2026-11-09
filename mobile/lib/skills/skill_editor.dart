import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/providers.dart';
import '../live/live_connection.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';

typedef Json = Map<String, dynamic>;

/// A skill's name, Use when and steps. A save carries the revision it read;
/// a 409 offers Load the latest or Keep mine. Existing skills also list the
/// bots with a switch each.
class SkillEditor extends ConsumerStatefulWidget {
  const SkillEditor({super.key, this.skill});

  final Json? skill;

  @override
  ConsumerState<SkillEditor> createState() => _SkillEditorState();
}

class _SkillEditorState extends ConsumerState<SkillEditor> {
  late final _name = TextEditingController(text: _s('name'));
  late final _useWhen = TextEditingController(text: _s('use_when'));
  late final _body = TextEditingController(text: _s('body'));
  late int _revision = (widget.skill?['revision'] as num?)?.toInt() ?? 0;
  Json? _conflict;
  bool _busy = false;

  String _s(String k) => widget.skill?[k] as String? ?? '';
  String? get _id => widget.skill?['id'] as String?;

  @override
  void dispose() {
    _name.dispose();
    _useWhen.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final fields = {
      'name': _name.text.trim(),
      'use_when': _useWhen.text.trim(),
      'body': _body.text,
    };
    setState(() => _busy = true);
    final api = ref.read(apiClientProvider);
    try {
      if (_id == null) {
        await api.post('/api/skills', fields);
      } else {
        await api.put('/api/skills/${Uri.encodeComponent(_id!)}',
            {...fields, 'base_revision': _revision});
      }
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (e.isConflict && e.current != null) {
        setState(() => _conflict = e.current);
      } else {
        _say(e.message);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _say(String s) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(s)));
  }

  void _loadLatest() {
    final c = _conflict!;
    _name.text = c['name'] as String? ?? '';
    _useWhen.text = c['use_when'] as String? ?? '';
    _body.text = c['body'] as String? ?? '';
    setState(() {
      _revision = (c['revision'] as num?)?.toInt() ?? _revision;
      _conflict = null;
    });
  }

  void _keepMine() => setState(() {
        _revision = (_conflict!['revision'] as num?)?.toInt() ?? _revision;
        _conflict = null;
      });

  Future<void> _delete() async {
    if (!await confirm(context, 'Delete this skill?', 'Delete')) return;
    if (!mounted) return;
    final ok = await attempt(context, () async {
      await ref.read(apiClientProvider).delete('/api/skills/${Uri.encodeComponent(_id!)}');
    });
    if (ok && mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_id == null ? 'New skill' : 'Skill'),
        actions: [
          if (_id != null)
            IconButton(
                tooltip: 'Delete', icon: const Icon(Icons.delete_outline), onPressed: _delete),
          TextButton(
              key: const Key('skill-save'),
              onPressed: _busy ? null : _save,
              child: const Text('Save skill')),
        ],
      ),
      body: ListView(padding: const EdgeInsets.all(Tokens.space4), children: [
        if (_conflict != null)
          MaterialBanner(
            backgroundColor: Tokens.raised,
            content: const Text('This changed somewhere else since you opened it.'),
            actions: [
              TextButton(onPressed: _loadLatest, child: const Text('Load the latest')),
              TextButton(onPressed: _keepMine, child: const Text('Keep mine')),
            ],
          ),
        TextField(controller: _name, decoration: const InputDecoration(labelText: 'Name')),
        const SizedBox(height: Tokens.space3),
        TextField(
            controller: _useWhen,
            decoration: const InputDecoration(
                labelText: 'Use when', helperText: 'The one line that says when it fits')),
        const SizedBox(height: Tokens.space3),
        TextField(
            controller: _body,
            minLines: 6,
            maxLines: 16,
            decoration: const InputDecoration(labelText: 'Steps')),
        if (_id != null) ...[
          const SizedBox(height: Tokens.space4),
          const Text('On for', style: TextStyle(color: Tokens.textSecondary)),
          _PerBot(skillId: _id!),
        ],
      ]),
    );
  }
}

class _PerBot extends ConsumerWidget {
  const _PerBot({required this.skillId});

  final String skillId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bots = ref.watch(liveProvider).bots.values.toList();
    return Column(children: [for (final b in bots) _BotSwitch(skillId: skillId, botId: b.id, name: b.name)]);
  }
}

class _BotSwitch extends ConsumerStatefulWidget {
  const _BotSwitch({required this.skillId, required this.botId, required this.name});

  final String skillId, botId, name;

  @override
  ConsumerState<_BotSwitch> createState() => _BotSwitchState();
}

class _BotSwitchState extends ConsumerState<_BotSwitch> {
  bool? _on;

  @override
  void initState() {
    super.initState();
    _read();
  }

  Future<void> _read() async {
    try {
      final data = await ref
          .read(apiClientProvider)
          .get('/api/skills?bot_id=${Uri.encodeComponent(widget.botId)}') as List;
      final mine = data.cast<Map>().where((s) => s['id'] == widget.skillId);
      if (mounted) setState(() => _on = mine.isNotEmpty && mine.first['on'] == true);
    } catch (_) {
      if (mounted) setState(() => _on = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(widget.name),
      value: _on ?? false,
      onChanged: _on == null
          ? null
          : (on) async {
              final ok = await attempt(
                  context,
                  () => ref.read(apiClientProvider).put(
                      '/api/bots/${widget.botId}/skills/${Uri.encodeComponent(widget.skillId)}',
                      {'on': on}));
              if (ok && mounted) setState(() => _on = on);
            },
    );
  }
}
