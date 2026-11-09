import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/common/widgets.dart';
import '../../board/tasks/task_models.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import 'filter_pill.dart';
import 'filter_store.dart';
import 'task_filter.dart';
import 'tasks_data.dart';
import 'work_projects.dart';

/// One row of toggle chips that scrolls sideways: Today · Overdue ·
/// Upcoming · High priority · No date · Done, a thin line, then each
/// project with its colour dot and No project. None on is All.
class FilterBar extends ConsumerWidget {
  const FilterBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final f = ref.watch(taskFilterProvider);
    final c = ref.read(taskFilterProvider.notifier);
    final open = ref.watch(openTasksProvider);
    final projects = chipProjects(
      ref.watch(workProjectsProvider).value ?? const [],
    );
    final chips = <Widget>[
      ..._statusChips(f, c, open),
      const _Rule(),
      for (final p in projects)
        FilterPill(
          key: Key('fchip-p-${p.id}'),
          label: p.name,
          dot: p.color == null ? Tokens.textFaint : hexColor(p.color),
          on: f.projects.contains(p.id),
          onTap: () => c.toggleProject(p.id),
        ),
      FilterPill(
        key: const Key('fchip-p-$noProject'),
        label: 'No project',
        dot: Tokens.textFaint,
        on: f.projects.contains(noProject),
        onTap: () => c.toggleProject(noProject),
      ),
    ];
    return SizedBox(
      height: Tokens.chipBarHeight,
      child: SingleChildScrollView(
        key: const Key('filter-bar'),
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(
          horizontal: Tokens.space4,
          vertical: Tokens.space2,
        ),
        child: Row(
          children: [
            for (final (i, chip) in chips.indexed) ...[
              if (i > 0) const SizedBox(width: Tokens.space2),
              chip,
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _statusChips(
    TaskFilter f,
    TaskFilterController c,
    List<TaskItem> open,
  ) => [
    if (!f.isEmpty) _ClearPill(count: f.activeCount, onTap: c.clear),
    for (final d in const [
      DateFilter.today,
      DateFilter.overdue,
      DateFilter.upcoming,
    ])
      _dateChip(d, f, c, open),
    FilterPill(
      key: const Key('fchip-high'),
      label: 'High priority',
      kind: PillKind.high,
      on: f.high,
      count: highCount(open),
      onTap: c.toggleHigh,
    ),
    _dateChip(DateFilter.noDate, f, c, open),
    FilterPill(
      key: const Key('fchip-done'),
      label: 'Done',
      on: f.done,
      onTap: c.toggleDone,
    ),
  ];

  Widget _dateChip(
    DateFilter d,
    TaskFilter f,
    TaskFilterController c,
    List<TaskItem> open,
  ) => FilterPill(
    key: Key('fchip-${d.id}'),
    label: d.label,
    kind: d == DateFilter.overdue ? PillKind.late : PillKind.plain,
    on: f.dates.contains(d),
    count: d == DateFilter.noDate ? null : countFor(d, open),
    onTap: () => c.toggleDate(d),
  );
}

/// The thin line between the status chips and the projects.
class _Rule extends StatelessWidget {
  const _Rule();

  @override
  Widget build(BuildContext context) => const Center(
    child: SizedBox(
      width: 1,
      height: Tokens.space5,
      child: ColoredBox(color: Tokens.borderStrong),
    ),
  );
}

/// The first chip while any are on: how many, and a tap turns them all
/// off. It keeps the filter visible when the lit chips are scrolled away.
class _ClearPill extends StatelessWidget {
  const _ClearPill({required this.count, required this.onTap});

  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = pillColors(PillKind.plain, AccentColors.of(context), on: true);
    return Tooltip(
      message: 'Clear filters',
      child: Material(
        key: const Key('fchip-clear'),
        color: c.bg,
        shape: StadiumBorder(side: BorderSide(color: c.border)),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: SizedBox(
            height: Tokens.chipHeight,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Tokens.space2),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.close, size: 16, color: c.fg),
                  const SizedBox(width: Tokens.space1),
                  Text(
                    '$count',
                    style: TextStyle(
                      color: c.fg,
                      fontSize: Tokens.fsLabel,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
