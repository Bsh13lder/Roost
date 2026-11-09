import '../../api/api_error.dart';
import 'task_models.dart';
import 'task_repo.dart';

final _lineBreak = RegExp(r'\r?\n');

/// True when pasted text holds more than one non-empty line: a list, not a
/// task (as the web's quick add reads it).
bool isPastedList(String text) =>
    text.split(_lineBreak).where((row) => row.trim().isNotEmpty).length > 1;

/// "Add 1 task", "Add 3 tasks".
String addTasksLabel(int count) => 'Add $count task${count == 1 ? '' : 's'}';

/// One task of a pasted list: the server's reading of its line and its
/// indented lines as steps.
class PastedTask {
  const PastedTask(this.reading, this.steps);

  final QuickReading reading;
  final List<String> steps;

  /// The body for `POST /api/tasks`: exactly what the server read. A pasted
  /// line never hands a task to a bot (the server refuses that line).
  Map<String, dynamic> createBody() => {
        ...reading.toTaskIn(),
        if (steps.isNotEmpty) 'steps': steps,
      };
}

/// What `POST /api/tasks/parse-many` read from a pasted list: the tasks, and
/// whether every line can be added (else the first problem, with its line).
class PastedList {
  const PastedList({
    required this.tasks,
    required this.ready,
    this.problem,
  });

  final List<PastedTask> tasks;
  final bool ready;
  final String? problem;

  int get count => tasks.length;

  factory PastedList.fromJson(Map<String, dynamic> json) {
    final raw = json['tasks'];
    final tasks = <PastedTask>[
      for (final t in raw is List ? raw.whereType<Map>() : const <Map>[])
        PastedTask(
          QuickReading(t.cast<String, dynamic>()),
          List.unmodifiable([for (final s in (t['steps'] as List? ?? const [])) '$s']),
        ),
    ];
    final problem = json['problem'];
    return PastedList(
      tasks: List.unmodifiable(tasks),
      ready: json['ready'] == true && tasks.isNotEmpty,
      problem: problem is String && problem.isNotEmpty ? problem : null,
    );
  }

  /// The same list with only [left] still to add.
  PastedList withTasks(List<PastedTask> left) =>
      PastedList(tasks: List.unmodifiable(left), ready: ready, problem: problem);
}

/// An add that stopped partway: [left] are the tasks not added yet.
class PasteAddProblem implements Exception {
  const PasteAddProblem(this.message, this.left);

  final String message;
  final List<PastedTask> left;

  @override
  String toString() => message;
}

/// Creates each task in order, one at a time. Throws [PasteAddProblem] with
/// the tasks still to add when one fails.
Future<List<TaskItem>> addPastedTasks(TaskRepo repo, List<PastedTask> tasks) async {
  final added = <TaskItem>[];
  for (var i = 0; i < tasks.length; i++) {
    try {
      added.add(await repo.create(tasks[i].createBody()));
    } on ApiException catch (e) {
      throw PasteAddProblem(e.message, List.unmodifiable(tasks.sublist(i)));
    }
  }
  return List.unmodifiable(added);
}
