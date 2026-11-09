import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'skill_editor.dart';

typedef Json = Map<String, dynamic>;

/// Every saved how-to (Skill). Tap one to edit it and switch it per bot.
class SkillsScreen extends ConsumerStatefulWidget {
  const SkillsScreen({super.key});

  @override
  ConsumerState<SkillsScreen> createState() => _SkillsScreenState();
}

class _SkillsScreenState extends ConsumerState<SkillsScreen> {
  late Future<List<Json>> _future = _load();

  Future<List<Json>> _load() async {
    final data = await ref.read(apiClientProvider).get('/api/skills') as List;
    return [for (final s in data) (s as Map).cast<String, dynamic>()];
  }

  Future<void> _open([Json? skill]) async {
    final changed = await Navigator.of(context).push<bool>(MaterialPageRoute(
        builder: (_) => SkillEditor(skill: skill)));
    if (changed == true) setState(() => _future = _load());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Skills'), actions: [
        IconButton(
            key: const Key('new-skill'),
            tooltip: 'New skill',
            icon: const Icon(Icons.add),
            onPressed: _open),
      ]),
      body: FutureBuilder<List<Json>>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) {
            return Center(
                child: TextButton(
                    onPressed: () => setState(() => _future = _load()),
                    child: Text('${describe(snap.error!)} Try again')));
          }
          final skills = snap.data;
          if (skills == null) {
            return const Center(child: CircularProgressIndicator());
          }
          if (skills.isEmpty) {
            return const Padding(
                padding: EdgeInsets.all(Tokens.space4),
                child: Quiet('No skills yet. A skill is a how-to every bot can reuse.'));
          }
          return ListView(children: [
            for (final s in skills)
              ListTile(
                title: Text('${s['name'] ?? ''}'),
                subtitle: Text('${s['use_when'] ?? ''}'),
                trailing: s['tainted'] == true
                    ? const Text('from web content',
                        style: TextStyle(
                            fontSize: Tokens.fsCaption,
                            color: Tokens.textFaint))
                    : null,
                onTap: () => _open(s),
              ),
          ]);
        },
      ),
    );
  }
}
