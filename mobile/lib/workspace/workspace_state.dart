import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// The Workspace's three views, in the bottom bar's order.
enum WorkspaceSection {
  tasks('Tasks', Icons.check_box_outlined),
  notes('Notes', Icons.folder_outlined),
  calendar('Calendar', Icons.calendar_month_outlined);

  const WorkspaceSection(this.label, this.icon);
  final String label;
  final IconData icon;
}

final workspaceSectionProvider =
    StateProvider.autoDispose<WorkspaceSection>((_) => WorkspaceSection.tasks);

/// What is typed in the bottom bar; every view filters by it as you type.
final workspaceQueryProvider = StateProvider.autoDispose<String>((_) => '');

/// True when every word of [query] is in [text], ignoring case.
bool matchesQuery(String text, String query) {
  final words = query.toLowerCase().split(RegExp(r'\s+')).where((w) => w.isNotEmpty);
  final hay = text.toLowerCase();
  return words.every(hay.contains);
}
