import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/projects/projects_api.dart';
import '../../board/tasks/task_repo.dart';

/// A project filter's id for the tasks in no project (the old Inbox).
const noProject = 'none';

/// One project as the Workspace shows it: a name, its colour and pin.
class ProjectInfo {
  const ProjectInfo({
    required this.id,
    required this.name,
    this.color,
    this.pinned = false,
    this.archived = false,
  });

  factory ProjectInfo.fromJson(Map<String, dynamic> j) => ProjectInfo(
        id: j['id'] as String,
        name: j['name'] as String? ?? '',
        color: j['color'] as String?,
        pinned: j['pinned'] == true,
        archived: j['status'] == 'archived',
      );

  final String id;
  final String name;
  final String? color;
  final bool pinned;
  final bool archived;
}

/// The filter chips' projects: pinned first, archived ones left out.
List<ProjectInfo> chipProjects(List<ProjectInfo> all) => [
      ...all.where((p) => p.pinned && !p.archived),
      ...all.where((p) => !p.pinned && !p.archived),
    ];

final workProjectsProvider =
    FutureProvider.autoDispose<List<ProjectInfo>>((ref) async {
  reloadOnTasksChanged(ref);
  final list = await ref.watch(projectsApiProvider).list();
  return [for (final j in list) ProjectInfo.fromJson(j)];
});

/// How Tasks are laid out: the day list or the Kanban. (The Calendar is
/// the Workspace's own section.)
enum TaskLayout { list, kanban }

final workLayoutProvider =
    StateProvider.autoDispose<TaskLayout>((_) => TaskLayout.list);
