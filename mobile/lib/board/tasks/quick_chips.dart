// The quick line's chips, drawn only from the server's reading (ported from
// the web's quickChips.ts). A chip the server could not use as typed (a
// project to ask about, a refused budget) shows as typed, to fix ("ask"); a
// warning says something and never blocks. Pure.

import 'task_models.dart';

enum ChipTone { read, ask, warn }

class QuickChip {
  const QuickChip(this.kind, this.label,
      {this.tone = ChipTone.read, this.words = const [], this.id, this.confirmBot});

  /// A server kind ("date", "priority", …), or "warning", "day-badge",
  /// "picked-reminder".
  final String kind;
  final String label;
  final ChipTone tone;

  /// The typed words this chip came from; × keeps them as plain text.
  final List<String> words;
  final String? id;

  /// The @bot chip: tap to confirm handing the task over.
  final String? confirmBot;

  String get key => id ?? kind;

  bool get removable => kind != 'warning' && kind != 'day-badge';

  QuickChip withWords(List<String> w) =>
      QuickChip(kind, label, tone: tone, words: w, id: id, confirmBot: confirmBot);
}

const _minutesPerHour = 60;

/// "1h 30m", "45m", "2h".
String formatEstimate(int minutes) {
  final h = minutes ~/ _minutesPerHour;
  final m = minutes % _minutesPerHour;
  return [if (h > 0) '${h}h', if (m > 0) '${m}m'].join(' ');
}

List<QuickChip> _dateChip(QuickReading r, String? dayBadge) {
  final named = r.matches['date']?.isNotEmpty ?? false;
  if (dayBadge != null && !named) return [QuickChip('day-badge', dayBadge)];
  final text = r.dueText;
  if (r.json['due_date'] == null || text == null || text.isEmpty) return const [];
  return [QuickChip('date', 'Due $text')];
}

List<QuickChip> _reminderChip(QuickReading r, String? remindLabel) {
  if (remindLabel != null) return [QuickChip('picked-reminder', remindLabel)];
  final text = r.reminderText;
  if (r.json['reminder_at'] != null && text != null) {
    return [QuickChip('reminder', 'Remind $text')];
  }
  final words = r.reminderWords;
  return words == null ? const [] : [QuickChip('reminder', words, tone: ChipTone.warn)];
}

List<QuickChip> _repeatChip(QuickReading r) {
  if (r.json['recurring'] != null) {
    return [QuickChip('repeat', r.repeatText ?? '${r.json['recurring']}')];
  }
  final words = r.repeatWords;
  return words == null ? const [] : [QuickChip('repeat', words, tone: ChipTone.ask)];
}

List<QuickChip> _projectChips(QuickReading r) {
  final name = r.projectName;
  final words = r.budgetWords;
  final budget = r.budget;
  final math = r.json['budget_math'] as String?;
  return [
    if (name != null) QuickChip('project', '/$name')
    else if (r.projectWords != null) QuickChip('project', r.projectWords!, tone: ChipTone.ask),
    // With no project the server reads it in General's currency (owner, 2026-10-26).
    if (budget != null)
      QuickChip('budget', math == null ? 'Budget $budget' : 'Budget $budget = $math')
    else if (words != null) QuickChip('budget', words, tone: ChipTone.ask),
  ];
}

List<QuickChip> _assigneeChip(QuickReading r, String? confirmedBot) {
  final bot = r.assignee;
  if (bot != null) {
    return bot.id == confirmedBot
        ? [QuickChip('assignee', 'Handing to ${bot.name}')]
        : [QuickChip('assignee', 'Assign to ${bot.name}', confirmBot: bot.id)];
  }
  final words = r.assigneeWords;
  return words == null ? const [] : [QuickChip('assignee', words, tone: ChipTone.ask)];
}

List<QuickChip> _plainChips(QuickReading r) => [
      if (r.priority != null) QuickChip('priority', '!${r.priority}'),
      for (final t in r.tags) QuickChip('tag', '#$t', id: 'tag-$t', words: ['#$t']),
      if (r.starred) const QuickChip('star', 'Starred'),
      if (r.estimateMinutes != null)
        QuickChip('estimate', '~${formatEstimate(r.estimateMinutes!)}'),
    ];

/// The chips for [reading], each with the words it came from. [dayBadge]
/// ("Due Wed 21 Oct") stands in while the line names no day; [remindLabel]
/// is a Remind me pick, which replaces any reminder the line names.
List<QuickChip> chipsOf(QuickReading reading,
    {String? dayBadge, String? remindLabel, String? confirmedBot}) {
  final matches = reading.matches;
  final chips = [
    ..._dateChip(reading, dayBadge),
    ..._reminderChip(reading, remindLabel),
    ..._repeatChip(reading),
    ..._projectChips(reading),
    ..._plainChips(reading),
    ..._assigneeChip(reading, confirmedBot),
    for (final w in reading.warnings) QuickChip('warning', w, tone: ChipTone.warn),
  ];
  return [
    for (final c in chips)
      c.words.isEmpty && (matches[c.kind]?.isNotEmpty ?? false)
          ? c.withWords(matches[c.kind]!)
          : c,
  ];
}
