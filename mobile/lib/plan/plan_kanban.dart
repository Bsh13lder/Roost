import 'package:flutter/material.dart';

import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'plan_models.dart';

/// Planned · On it · Done as stacked sections; "Move to…" changes the column.
class PlanKanban extends StatelessWidget {
  const PlanKanban({super.key, required this.items, required this.onMove});

  final List<PlanItem> items;
  final void Function(PlanItem item, String status) onMove;

  @override
  Widget build(BuildContext context) {
    return ListView(children: [
      for (final status in planStatuses) ...[
        Padding(
          padding: const EdgeInsets.fromLTRB(
              Tokens.space4, Tokens.space3, Tokens.space4, Tokens.space1),
          child: Text(planStatusLabel(status).toUpperCase(),
              style: const TextStyle(
                  color: Tokens.textFaint,
                  fontSize: Tokens.fsCaption,
                  letterSpacing: 0.8)),
        ),
        ..._column(status),
      ],
    ]);
  }

  List<Widget> _column(String status) {
    final rows = [for (final i in items) if (i.status == status) i];
    if (rows.isEmpty) {
      return const [
        Padding(
            padding: EdgeInsets.symmetric(horizontal: Tokens.space4),
            child: Quiet('Nothing here.'))
      ];
    }
    return [for (final i in rows) _ItemTile(item: i, onMove: onMove)];
  }
}

String planWhen(PlanItem i) =>
    [if (i.date != null) i.date!, if (i.time != null) i.time!].join(' ');

class _ItemTile extends StatelessWidget {
  const _ItemTile({required this.item, required this.onMove});

  final PlanItem item;
  final void Function(PlanItem item, String status) onMove;

  @override
  Widget build(BuildContext context) {
    final when = planWhen(item);
    final sub = [if (when.isNotEmpty) when, if (item.tainted) 'from web content']
        .join(' · ');
    return ListTile(
      title: Text(item.text),
      subtitle: sub.isEmpty ? null : Text(sub),
      trailing: item.id == null
          ? null
          : PopupMenuButton<String>(
              tooltip: 'Move to…',
              icon: const Icon(Icons.more_vert),
              onSelected: (s) => onMove(item, s),
              itemBuilder: (_) => [
                for (final s in planStatuses)
                  if (s != item.status)
                    PopupMenuItem(
                        value: s, child: Text('Move to ${planStatusLabel(s)}')),
              ],
            ),
    );
  }
}
