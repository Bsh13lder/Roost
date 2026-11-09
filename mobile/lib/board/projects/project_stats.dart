import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import '../common/format.dart';
import '../common/widgets.dart';
import 'projects_api.dart';

/// The top of a project's page: name, status, facts and the three stats
/// (total budget, this month, tasks). Every amount, percent and tone is the
/// server's.
class ProjectHeaderCard extends StatelessWidget {
  const ProjectHeaderCard({super.key, required this.project});

  final Json project;

  @override
  Widget build(BuildContext context) {
    final p = project;
    final currency = p['currency'] as String;
    final facts = [
      if (p['lead_bot_name'] != null) 'Led by ${p['lead_bot_name']}',
      if (p['start_date'] != null && p['due_date'] != null)
        '${dayLabel(p['start_date'] as String)} → ${dayLabel(p['due_date'] as String)}'
      else if (p['due_date'] != null)
        'Due ${dayLabel(p['due_date'] as String)}',
    ].join(' · ');
    return Card(
      color: Tokens.panel,
      margin: const EdgeInsets.all(Tokens.space4),
      child: Padding(
        padding: const EdgeInsets.all(Tokens.space4),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            CircleAvatar(radius: 6, backgroundColor: hexColor(p['color'] as String?)),
            const SizedBox(width: Tokens.space2),
            Expanded(
              child: Text('${p['name']}',
                  style: const TextStyle(fontSize: Tokens.fsTitle, fontWeight: FontWeight.w600)),
            ),
            Text(p['status'] == 'archived' ? 'Archived' : 'Active',
                style: TextStyle(color: p['status'] == 'archived' ? Tokens.textFaint : Tokens.ok)),
          ]),
          if (facts.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: Tokens.space2),
              child: Text(facts, style: const TextStyle(color: Tokens.textSecondary)),
            ),
          const SizedBox(height: Tokens.space3),
          _budget('Total budget', p['total'] as Map, currency),
          _budget('This month', p['month'] as Map, currency),
          _tasks(p['progress'] as Map, currency),
          for (final e in ((p['other_currencies'] as Map?) ?? const {}).entries)
            Text('Also ${formatMoney('${e.value}', '${e.key}')} (not in the total)',
                style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          for (final e in ((p['money_in'] as Map?) ?? const {}).entries)
            Text('Money in ${formatMoney('${e.value}', '${e.key}')}',
                style: const TextStyle(color: Tokens.ok, fontSize: Tokens.fsLabel)),
        ]),
      ),
    );
  }

  Widget _stat(String eyebrow, String value, String sub, Widget? bar) => Padding(
        padding: const EdgeInsets.only(bottom: Tokens.space3),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(eyebrow.toUpperCase(),
              style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
          Text(value, style: const TextStyle(fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
          if (bar != null) Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: bar),
          Text(sub, style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
        ]),
      );

  Widget _budget(String eyebrow, Map line, String currency) {
    final spent = formatMoney('${line['spent']}', currency);
    if (line['budget'] == null) {
      return _stat(eyebrow, 'No limit', '$spent spent', null);
    }
    final remaining = '${line['remaining'] ?? '0'}';
    final over = remaining.startsWith('-');
    return _stat(
      eyebrow,
      '${formatMoney(unsigned(remaining), currency)} ${over ? 'over' : 'left of'} ${formatMoney('${line['budget']}', currency)}',
      '$spent spent · ${line['used_percent']}%',
      ToneBar(percent: line['used_percent'] as num?, tone: line['tone'] as String?),
    );
  }

  Widget _tasks(Map progress, String currency) {
    final total = progress['total'] as int;
    final done = progress['done'] as int;
    final parts = [
      if ((progress['overdue'] as int) > 0) '${progress['overdue']} overdue',
      if ((progress['steps_total'] as int) > 0)
        '${progress['steps_done']} of ${progress['steps_total']} steps done',
      if ((double.tryParse('${progress['planned_total']}') ?? 0) > 0)
        '${formatMoney('${progress['planned_total']}', currency)} planned',
    ];
    return _stat(
      'Tasks',
      '$done of $total done',
      parts.isEmpty ? 'Nothing planned yet' : parts.join(' · '),
      ToneBar(percent: total > 0 ? done * 100 / total : 0),
    );
  }
}
