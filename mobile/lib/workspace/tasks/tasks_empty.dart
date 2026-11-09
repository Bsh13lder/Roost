import 'package:flutter/material.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import 'task_filter.dart';

/// The words for an empty list: all clear, or nothing matches.
({String line, bool canClear}) emptyWords(TaskFilter f, String typed) {
  if (typed.trim().isNotEmpty) {
    return (line: 'No task matches “${typed.trim()}”', canClear: !f.isEmpty);
  }
  if (f.isEmpty) return (line: 'All clear. Nothing on your list.', canClear: false);
  if (f == const TaskFilter().toggleDate(DateFilter.today)) {
    return (line: 'All clear for today', canClear: false);
  }
  return (line: 'No tasks match these filters', canClear: true);
}

/// A friendly icon, one line, and Clear filters when chips hide the tasks.
class TasksEmpty extends StatelessWidget {
  const TasksEmpty({
    super.key,
    required this.filter,
    required this.typed,
    required this.onClear,
  });

  final TaskFilter filter;
  final String typed;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final w = emptyWords(filter, typed);
    final accent = AccentColors.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: Tokens.space6, vertical: Tokens.space8 * 2),
      child: Column(children: [
        Icon(w.canClear ? Icons.filter_alt_off_outlined : Icons.task_alt,
            size: 48, color: accent.strong),
        const SizedBox(height: Tokens.space4),
        Text(w.line,
            textAlign: TextAlign.center,
            style: const TextStyle(
                color: Tokens.text,
                fontSize: Tokens.fsLead,
                fontWeight: FontWeight.w600)),
        if (w.canClear) ...[
          const SizedBox(height: Tokens.space3),
          TextButton(
            key: const Key('filters-clear'),
            onPressed: onClear,
            child: Text('Clear filters', style: TextStyle(color: accent.strong)),
          ),
        ],
      ]),
    );
  }
}
