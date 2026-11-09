import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import '../common/format.dart';
import '../common/widgets.dart';
import 'money_api.dart';

/// One expense row: project dot, words, and the amount (income apart, in green).
class ExpenseTile extends StatelessWidget {
  const ExpenseTile({super.key, required this.expense, required this.onTap});

  final Json expense;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final e = expense;
    final income = e['kind'] == 'income';
    final isVoid = e['status'] == 'void';
    final title = (e['description'] as String?)?.isNotEmpty == true
        ? e['description'] as String
        : (e['vendor'] as String?) ?? (e['project'] as String? ?? '');
    final sub = [
      e['project'],
      if (e['vendor'] != null && e['description'] != null) e['vendor'],
      if (e['repeat'] != null) 'repeats ${e['repeat']}',
      if (isVoid) 'void',
      if (e['tainted'] == true) 'from web content',
    ].where((p) => p != null && '$p'.isNotEmpty).join(' · ');
    final amount = formatMoney(e['amount'] as String, e['currency'] as String);
    return ListTile(
      onTap: onTap,
      dense: true,
      leading: CircleAvatar(
          radius: 5, backgroundColor: hexColor(e['project_color'] as String?)),
      title: Text(
        '${e['is_favorite'] == true ? '★ ' : ''}$title',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: isVoid ? Tokens.textFaint : Tokens.text,
          decoration: isVoid ? TextDecoration.lineThrough : null,
        ),
      ),
      subtitle: Text(sub,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: Tokens.textSecondary)),
      trailing: Text(
        income ? '+$amount' : amount,
        style: TextStyle(
          color: income ? Tokens.ok : Tokens.text,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

/// The server's range summary: "12 expenses · €340.20 this week".
class RangeSummaryLine extends StatelessWidget {
  const RangeSummaryLine({
    super.key,
    required this.count,
    required this.totals,
    required this.currency,
    this.label = '',
  });

  final int count;
  final Map totals;
  final String currency;
  final String label;

  @override
  Widget build(BuildContext context) {
    final money = [
      for (final e in totals.entries) formatMoney('${e.value}', '${e.key}'),
    ];
    final figures = [
      '$count ${count == 1 ? 'expense' : 'expenses'}',
      ...(money.isEmpty ? [formatMoney('0', currency)] : money),
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: Tokens.space4, vertical: Tokens.space2),
      child: Text(
        '${figures.join(' · ')}${label.isEmpty ? '' : ' $label'}; other currencies apart',
        key: const ValueKey('range-summary'),
        style: const TextStyle(
            color: Tokens.textSecondary, fontSize: Tokens.fsLabel),
      ),
    );
  }
}

/// List view: expenses under a heading per day, with the server's day total.
class ExpenseDays extends StatelessWidget {
  const ExpenseDays({super.key, required this.range, required this.onOpen});

  final Json range;
  final void Function(Json expense) onOpen;

  @override
  Widget build(BuildContext context) {
    final expenses = [
      for (final e in (range['expenses'] as List)) Map<String, dynamic>.from(e as Map),
    ];
    final totals = {
      for (final d in (range['days'] as List))
        (d as Map)['day'] as String: d['totals'] as Map,
    };
    final days = <String>[];
    for (final e in expenses) {
      final day = e['spent_at'] as String;
      if (!days.contains(day)) days.add(day);
    }
    return Column(children: [
      for (final day in days) ...[
        SectionTitle(
          dayLabel(day),
          trailing: Text(
            [for (final t in (totals[day] ?? {}).entries) formatMoney('${t.value}', '${t.key}')].join(' · '),
            style: const TextStyle(color: Tokens.textSecondary),
          ),
        ),
        for (final e in expenses.where((e) => e['spent_at'] == day))
          ExpenseTile(expense: e, onTap: () => onOpen(e)),
      ],
    ]);
  }
}

/// By days view: a bar per day from the server's `bar_percent`.
class ExpenseBars extends StatelessWidget {
  const ExpenseBars({super.key, required this.range});

  final Json range;

  @override
  Widget build(BuildContext context) {
    final currency = range['currency'] as String? ?? 'EUR';
    return Column(children: [
      for (final d in (range['days'] as List))
        Padding(
          padding: const EdgeInsets.symmetric(
              horizontal: Tokens.space4, vertical: Tokens.space2),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(dayLabel((d as Map)['day'] as String))),
              Text(
                [for (final t in (d['totals'] as Map).entries) formatMoney('${t.value}', '${t.key}')].join(' · '),
                style: const TextStyle(color: Tokens.textSecondary),
              ),
            ]),
            const SizedBox(height: 4),
            ToneBar(percent: d['bar_percent'] as num?),
            Text('${d['count']} ${d['count'] == 1 ? 'expense' : 'expenses'} · $currency',
                style: const TextStyle(
                    color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
          ]),
        ),
    ]);
  }
}
