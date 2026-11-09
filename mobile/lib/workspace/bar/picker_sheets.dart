import 'package:flutter/material.dart';

import '../../board/tasks/quick_insert.dart';
import '../../board/tasks/quick_suggest.dart';
import '../../theme/tokens.dart';

const _titleStyle = TextStyle(fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600);

/// A short list to pick one of (Priority, Repeat).
Future<QuickChoice?> showChoiceSheet(
    BuildContext context, String title, List<QuickChoice> choices) {
  return showModalBottomSheet<QuickChoice>(
    context: context,
    showDragHandle: true,
    builder: (context) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Tokens.space4, 0, Tokens.space4, Tokens.space4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: _titleStyle),
            const SizedBox(height: Tokens.space2),
            for (final c in choices)
              ListTile(
                key: Key('choice-${c.key}'),
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text(c.label),
                trailing: Text(c.words,
                    style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsCaption)),
                onTap: () => Navigator.pop(context, c),
              ),
          ],
        ),
      ),
    ),
  );
}

/// Your projects, with a search line; answers the picked name.
Future<String?> showProjectSheet(BuildContext context, List<String> names) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _ProjectBody(names: names),
  );
}

class _ProjectBody extends StatefulWidget {
  const _ProjectBody({required this.names});

  final List<String> names;

  @override
  State<_ProjectBody> createState() => _ProjectBodyState();
}

class _ProjectBodyState extends State<_ProjectBody> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final shown = filterNames(widget.names, _query).take(maxSuggestions * 3).toList();
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(Tokens.space4, 0, Tokens.space4,
            Tokens.space4 + MediaQuery.viewInsetsOf(context).bottom),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Project', style: _titleStyle),
            const SizedBox(height: Tokens.space2),
            TextField(
              key: const Key('project-search'),
              decoration: const InputDecoration(hintText: 'Search projects', isDense: true),
              onChanged: (v) => setState(() => _query = v),
            ),
            const SizedBox(height: Tokens.space2),
            if (shown.isEmpty)
              const Padding(
                padding: EdgeInsets.all(Tokens.space3),
                child: Text('No project like that.',
                    style: TextStyle(color: Tokens.textSecondary)),
              ),
            for (final name in shown)
              ListTile(
                key: Key('project-$name'),
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.folder_outlined, size: 20),
                title: Text(name),
                onTap: () => Navigator.pop(context, name),
              ),
          ],
        ),
      ),
    );
  }
}
