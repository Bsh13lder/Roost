import 'package:flutter/foundation.dart';

const planStatuses = ['planned', 'on_it', 'done'];

String planStatusLabel(String status) => switch (status) {
      'planned' => 'Planned',
      'on_it' => 'On it',
      'done' => 'Done',
      'dropped' => 'Dropped',
      _ => status,
    };

@immutable
class PlanItem {
  const PlanItem({
    required this.id,
    required this.status,
    required this.text,
    required this.tags,
    required this.date,
    required this.time,
    required this.tainted,
  });

  factory PlanItem.fromJson(Map<String, dynamic> j) => PlanItem(
        id: j['id'] as String?,
        status: j['status'] as String? ?? 'planned',
        text: j['text'] as String? ?? '',
        tags: [for (final t in (j['tags'] as List? ?? const [])) '$t'],
        date: j['date'] as String?,
        time: j['time'] as String?,
        tainted: j['tainted'] == true,
      );

  /// An item without an id cannot be moved.
  final String? id;
  final String status, text;
  final List<String> tags;
  final String? date, time;
  final bool tainted;
}

/// The whole Plan as the server answers it: the text, its revision, its items.
@immutable
class PlanData {
  const PlanData({
    required this.content,
    required this.revision,
    required this.unreadable,
    required this.items,
  });

  factory PlanData.fromJson(Map<String, dynamic> j) => PlanData(
        content: j['content'] as String? ?? '',
        revision: (j['revision'] as num?)?.toInt() ?? 1,
        unreadable: (j['unreadable'] as num?)?.toInt() ?? 0,
        items: [
          for (final i in (j['items'] as List? ?? const []))
            PlanItem.fromJson((i as Map).cast<String, dynamic>()),
        ],
      );

  final String content;
  final int revision, unreadable;
  final List<PlanItem> items;
}

/// Items by day, dated ones in date order, then the undated.
List<(String?, List<PlanItem>)> agendaDays(List<PlanItem> items) {
  final byDay = <String?, List<PlanItem>>{};
  for (final i in items) {
    if (i.status == 'dropped') continue;
    (byDay[i.date] ??= []).add(i);
  }
  for (final list in byDay.values) {
    list.sort((a, b) => (a.time ?? '99').compareTo(b.time ?? '99'));
  }
  final days = byDay.keys.whereType<String>().toList()..sort();
  return [
    for (final d in days) (d, byDay[d]!),
    if (byDay.containsKey(null)) (null, byDay[null]!),
  ];
}
