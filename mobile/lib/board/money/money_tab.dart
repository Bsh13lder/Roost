import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/format.dart';
import '../common/widgets.dart';
import 'expense_line.dart';
import 'expense_rows.dart';
import 'expense_sheet.dart';
import 'money_api.dart';
import 'period.dart';

/// The Board's Money tab: the expense line, a month with arrows, the period
/// picker, List · By days, and the server's range summary. [projectId] narrows
/// it to one project (a project page's money).
class MoneyTab extends ConsumerStatefulWidget {
  const MoneyTab({super.key, this.projectId});

  final String? projectId;

  @override
  ConsumerState<MoneyTab> createState() => _MoneyTabState();
}

class _MoneyTabState extends ConsumerState<MoneyTab> {
  late final String _thisMonth = appMonth();
  late String _month = _thisMonth;
  Period _period = Period.month;
  ({String from, String to})? _custom;
  bool _byDays = false;
  Future<({Json range, Json? summary})>? _data;

  @override
  void initState() {
    super.initState();
    _load();
  }

  ({String from, String to}) get _span => periodSpan(
      _period, _month, appTodayIso(), _custom);

  void _load() {
    final api = ref.read(moneyApiProvider);
    final span = _span;
    setState(() {
      _data = () async {
        final range =
            await api.range(span.from, span.to, projectId: widget.projectId);
        final summary = widget.projectId == null && _period == Period.month
            ? await api.summary(_month)
            : null;
        return (range: range, summary: summary);
      }();
    });
  }

  void _setMonth(int delta) {
    final next = shiftMonth(_month, delta);
    if (next.compareTo(_thisMonth) > 0) return;
    _month = next;
    _period = Period.month;
    _load();
  }

  Future<void> _pick(Period p) async {
    if (p == Period.custom) {
      final today = DateTime.parse(appTodayIso());
      final r = await showDateRangePicker(
        context: context,
        firstDate: DateTime(today.year - 5),
        lastDate: today,
      );
      if (r == null) return;
      _custom = (from: isoDay(r.start), to: isoDay(r.end));
    }
    _period = p;
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(children: [
      ExpenseLine(projectId: widget.projectId, onAdded: _load),
      _header(),
      FutureBuilder(
        future: _data,
        builder: (context, snap) {
          if (snap.hasError) return BoardNote(errorText(snap.error!), error: true);
          if (!snap.hasData) return const BoardNote('Loading…');
          return _body(snap.data!);
        },
      ),
    ]);
  }

  Widget _header() => Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space2),
        child: Row(children: [
          IconButton(
              tooltip: 'Previous month',
              onPressed: () => _setMonth(-1),
              icon: const Icon(Icons.chevron_left)),
          Expanded(
            child: Text(monthLabel(_month),
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: Tokens.fsLead)),
          ),
          IconButton(
              tooltip: 'Next month',
              onPressed: _month == _thisMonth ? null : () => _setMonth(1),
              icon: const Icon(Icons.chevron_right)),
          PopupMenuButton<Period>(
            tooltip: 'Pick a period',
            onSelected: _pick,
            child: Chip(label: Text(periodLabel(_period, _custom))),
            itemBuilder: (_) => [
              for (final p in Period.values)
                PopupMenuItem(value: p, child: Text(periodName(p))),
            ],
          ),
        ]),
      );

  Widget _body(({Json range, Json? summary}) d) {
    final range = d.range;
    final summary = range['summary'] as Map;
    final empty = (range['expenses'] as List).isEmpty;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (d.summary != null) _monthCard(d.summary!),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
        child: SegmentedButton<bool>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: false, label: Text('List')),
            ButtonSegment(value: true, label: Text('By days')),
          ],
          selected: {_byDays},
          onSelectionChanged: (s) => setState(() => _byDays = s.first),
        ),
      ),
      RangeSummaryLine(
        count: summary['count'] as int,
        totals: summary['totals'] as Map,
        currency: range['currency'] as String,
        label: _period == Period.month ? '' : periodLabel(_period, _custom).toLowerCase(),
      ),
      if (empty)
        BoardNote(_month == _thisMonth && _period == Period.month
            ? 'Nothing spent yet. Add an expense above.'
            : 'Nothing spent in this period.')
      else if (_byDays)
        ExpenseBars(range: range)
      else
        ExpenseDays(
          range: range,
          onOpen: (e) => showExpenseSheet(context, e, _load),
        ),
    ]);
  }

  /// The month's totals as the server reckons them; income sits apart.
  Widget _monthCard(Json s) {
    final currency = s['currency'] as String;
    final moneyIn = (s['money_in'] as Map?) ?? const {};
    return Card(
      color: Tokens.panel,
      margin: const EdgeInsets.all(Tokens.space4),
      child: Padding(
        padding: const EdgeInsets.all(Tokens.space4),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(formatMoney('${s['total']}', currency),
              key: const ValueKey('month-total'),
              style: const TextStyle(
                  fontSize: Tokens.fsDisplay, fontWeight: FontWeight.w600)),
          Text('spent · ${s['expense_count']} expenses',
              style: const TextStyle(color: Tokens.textSecondary)),
          for (final e in ((s['other_currencies'] as Map?) ?? const {}).entries)
            Text('Also ${formatMoney('${e.value}', '${e.key}')}',
                style: const TextStyle(color: Tokens.textSecondary)),
          for (final e in moneyIn.entries)
            Text('Money in ${formatMoney('${e.value}', '${e.key}')}',
                style: const TextStyle(color: Tokens.ok)),
        ]),
      ),
    );
  }
}
