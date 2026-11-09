import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/models.dart';
import '../api/providers.dart';
import '../features/home/home_data.dart';
import '../profile/avatar_editor.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';

typedef Json = Map<String, dynamic>;

/// New bot: a name, a job, an optional template and a look; then its chat.
class NewBotScreen extends ConsumerStatefulWidget {
  const NewBotScreen({super.key});

  @override
  ConsumerState<NewBotScreen> createState() => _NewBotScreenState();
}

class _NewBotScreenState extends ConsumerState<NewBotScreen> {
  final _name = TextEditingController();
  final _job = TextEditingController();
  Avatar _avatar = const Avatar();
  List<Json> _templates = const [];
  String? _templateId;
  String _instructions = '';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadTemplates();
  }

  @override
  void dispose() {
    _name.dispose();
    _job.dispose();
    super.dispose();
  }

  Future<void> _loadTemplates() async {
    try {
      final data = await ref.read(apiClientProvider).get('/api/templates') as List;
      if (mounted) {
        setState(() => _templates = [
              for (final t in data) (t as Map).cast<String, dynamic>(),
            ]);
      }
    } catch (_) {
      // Templates only fill the form; starting from nothing still works.
    }
  }

  void _pick(Json? t) {
    setState(() {
      _templateId = t?['id'] as String?;
      _instructions = t?['instructions'] as String? ?? '';
      if (t != null) {
        _name.text = t['name'] as String? ?? '';
        _job.text = t['job'] as String? ?? '';
        _avatar = Avatar.fromJson(t['avatar']);
      }
    });
  }

  Future<void> _create() async {
    if (_name.text.trim().isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Give the bot a name.')));
      return;
    }
    setState(() => _busy = true);
    String? id;
    final ok = await attempt(context, () async {
      final bot = await ref.read(apiClientProvider).post('/api/bots', {
        'name': _name.text.trim(),
        'job': _job.text.trim(),
        'instructions': _instructions,
        'avatar': _avatar.toJson(),
        if (_templateId != null) 'template_id': _templateId,
      });
      id = (bot as Map)['id'] as String;
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok && id != null) {
      ref.invalidate(botsLoadProvider);
      ref.invalidate(chatsProvider);
      context.pushReplacement('/chat/$id');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New bot')),
      body: ListView(padding: const EdgeInsets.all(Tokens.space4), children: [
        if (_templates.isNotEmpty) ...[
          const Text('Start from', style: TextStyle(color: Tokens.textSecondary)),
          Wrap(spacing: Tokens.space2, children: [
            ChoiceChip(
                label: const Text('Blank'),
                selected: _templateId == null,
                onSelected: (_) => _pick(null)),
            for (final t in _templates)
              ChoiceChip(
                  label: Text('${t['label'] ?? t['name']}'),
                  selected: _templateId == t['id'],
                  onSelected: (_) => _pick(t)),
          ]),
          const SizedBox(height: Tokens.space3),
        ],
        TextField(
            key: const Key('new-bot-name'),
            controller: _name,
            decoration: const InputDecoration(labelText: 'Name')),
        const SizedBox(height: Tokens.space3),
        TextField(
            controller: _job,
            decoration: const InputDecoration(labelText: 'Job')),
        const SizedBox(height: Tokens.space4),
        AvatarEditor(
            avatar: _avatar, onChanged: (a) => setState(() => _avatar = a)),
        const SizedBox(height: Tokens.space4),
        FilledButton(
          key: const Key('create-bot'),
          onPressed: _busy ? null : _create,
          child: const Text('Create'),
        ),
      ]),
    );
  }
}
