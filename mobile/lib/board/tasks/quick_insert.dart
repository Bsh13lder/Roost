// The quick line's pickers write the same words typing would, into the line
// (ported from the web's quickInsert.ts), so the server reads them like any
// other words and draws the same chip. Pure.

import 'task_dates.dart';

class QuickChoice {
  const QuickChoice(this.key, this.label, this.words);

  final String key;
  final String label;
  final String words;
}

const priorityChoices = [
  QuickChoice('urgent', 'Urgent', '!urgent'),
  QuickChoice('high', 'High', '!high'),
  QuickChoice('medium', 'Medium', '!medium'),
  QuickChoice('low', 'Low', '!low'),
];

const repeatChoices = [
  QuickChoice('day', 'Every day', 'every day'),
  QuickChoice('weekday', 'Every weekday', 'every weekday'),
  QuickChoice('week', 'Every week', 'every week'),
  QuickChoice('other-week', 'Every other week', 'every other week'),
  QuickChoice('month', 'Every month', 'every month'),
  QuickChoice('year', 'Every year', 'every year'),
];

/// A picked day as words the server reads: "2026-10-21", or
/// "2026-10-21 at 09:00" with a clock.
String dayWords(DateTime day, [String? clock]) =>
    clock == null ? isoDay(day) : '${isoDay(day)} at $clock';

/// [text] without the earlier [words] of a chip (whole words, any case).
String withoutWords(String text, List<String> words) {
  final longestFirst = [...words]..sort((a, b) => b.length - a.length);
  final cut = longestFirst.fold(text, (now, word) {
    final pattern = RegExp('(?<!\\w)${RegExp.escape(word)}(?!\\w)', caseSensitive: false);
    return now.replaceFirst(pattern, ' ');
  });
  return cut.replaceAll(RegExp(r'\s+'), ' ').trim();
}

/// The line with a picked chip's [words]: they replace the chip's earlier
/// words, or are added at the end. Empty words only remove (No date).
String insertWords(String text, String words, [List<String> replacing = const []]) {
  final base = withoutWords(text, replacing);
  return [base, words.trim()].where((s) => s.isNotEmpty).join(' ');
}

/// A tag as `#tag`; spaces and a leading # are dropped. Null when unusable.
String? tagWords(String raw) {
  final name = raw.trim().replaceFirst(RegExp(r'^#+'), '').replaceAll(RegExp(r'\s+'), '-');
  final ok = RegExp(r'^\p{L}[\p{L}\p{N}_-]*$', unicode: true).hasMatch(name);
  return ok ? '#$name' : null;
}

/// Names containing [query], those that start with it first.
List<String> filterNames(List<String> names, String query) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return [...names];
  final has = names.where((n) => n.toLowerCase().contains(q));
  return [
    ...has.where((n) => n.toLowerCase().startsWith(q)),
    ...has.where((n) => !n.toLowerCase().startsWith(q)),
  ];
}
