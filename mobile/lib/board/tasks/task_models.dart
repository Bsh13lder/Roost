// Wire shapes for the Board's Tasks (`task_out`, `GET /api/tasks/{id}`,
// `POST /api/tasks/parse`, comments). Immutable; the server does the sums.

class TaskStep {
  const TaskStep({required this.id, required this.title, required this.done});

  factory TaskStep.fromJson(Map<String, dynamic> j) => TaskStep(
        id: j['id'] as String,
        title: j['title'] as String? ?? '',
        done: j['done'] == true,
      );

  final String id;
  final String title;
  final bool done;

  Map<String, dynamic> toJson() => {'id': id, 'title': title, 'done': done};
}

class RowMoney {
  const RowMoney({required this.left, required this.currency, required this.over});

  factory RowMoney.fromJson(Map<String, dynamic> j) => RowMoney(
        left: j['left'] as String? ?? '0',
        currency: j['currency'] as String? ?? '',
        over: j['over'] == true,
      );

  final String left;
  final String currency;
  final bool over;

  Map<String, dynamic> toJson() =>
      {'left': left, 'currency': currency, 'over': over};
}

class TaskItem {
  const TaskItem({
    required this.id,
    required this.title,
    required this.status,
    required this.priority,
    this.description,
    this.dueDate,
    this.reminderAt,
    this.preReminders = const [],
    this.projectId,
    this.tags = const [],
    this.steps = const [],
    this.starred = false,
    this.dueBucket = 'none',
    this.owner = 'user',
    this.createdAt,
    this.updatedAt,
    this.completedAt,
    this.tainted = false,
    this.repeatText,
    this.money,
    this.commentCount = 0,
    this.createdByBot,
  });

  factory TaskItem.fromJson(Map<String, dynamic> j) => TaskItem(
        id: j['id'] as String,
        title: j['title'] as String? ?? '',
        status: j['status'] as String? ?? 'todo',
        priority: j['priority'] as String? ?? 'medium',
        description: j['description'] as String?,
        dueDate: j['due_date'] as String?,
        reminderAt: j['reminder_at'] as String?,
        preReminders: [
          for (final p in (j['pre_reminders'] as List? ?? const [])) '$p',
        ],
        projectId: j['project_id'] as String?,
        tags: [for (final t in (j['tags'] as List? ?? const [])) '$t'],
        steps: [
          for (final s in (j['steps'] as List? ?? const []))
            TaskStep.fromJson((s as Map).cast<String, dynamic>()),
        ],
        starred: j['starred'] == true,
        dueBucket: j['due_bucket'] as String? ?? 'none',
        owner: j['owner'] as String? ?? 'user',
        createdAt: j['created_at'] as String?,
        updatedAt: j['updated_at'] as String?,
        completedAt: j['completed_at'] as String?,
        tainted: j['tainted'] == true,
        repeatText: j['repeat_text'] as String?,
        commentCount: (j['comment_count'] as num?)?.toInt() ?? 0,
        createdByBot: j['created_by_bot'] as String?,
        money: j['money'] is Map && (j['money'] as Map).containsKey('left')
            ? RowMoney.fromJson((j['money'] as Map).cast<String, dynamic>())
            : null,
      );

  final String id;
  final String title;
  final String status;
  final String priority;
  final String? description;
  final String? dueDate;
  final String? reminderAt;
  final List<String> preReminders;
  final String? projectId;
  final List<String> tags;
  final List<TaskStep> steps;
  final bool starred;
  final String dueBucket;
  final String owner;
  final String? createdAt;
  final String? updatedAt;
  final String? completedAt;
  final bool tainted;
  final String? repeatText;
  final RowMoney? money;

  /// Live comments on the task, as the server counted them for a list row.
  final int commentCount;

  /// The bot that made it; null for you, or a bot since retired.
  final String? createdByBot;

  /// The same wire shape [TaskItem.fromJson] reads, for the phone's kept
  /// copy of the open list (offline tasks).
  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'status': status,
        'priority': priority,
        'description': description,
        'due_date': dueDate,
        'reminder_at': reminderAt,
        'pre_reminders': preReminders,
        'project_id': projectId,
        'tags': tags,
        'steps': [for (final s in steps) s.toJson()],
        'starred': starred,
        'due_bucket': dueBucket,
        'owner': owner,
        'created_at': createdAt,
        'updated_at': updatedAt,
        'completed_at': completedAt,
        'tainted': tainted,
        'repeat_text': repeatText,
        'money': money?.toJson(),
        'comment_count': commentCount,
        'created_by_bot': createdByBot,
      };

  /// A new task with [next] as its status; this one is left as it is.
  TaskItem withStatus(String next) =>
      TaskItem.fromJson({...toJson(), 'status': next});

  bool get isDone => status == 'done' || status == 'failed';
  bool get isOverdue => dueBucket == 'overdue';
  int get stepsDone => steps.where((s) => s.done).length;
}

/// The Board tab counts (`GET /api/tasks/counts`).
class TaskCounts {
  const TaskCounts({
    this.overdue = 0,
    this.today = 0,
    this.upcoming = 0,
    this.someday = 0,
    this.doneWeek = 0,
  });

  factory TaskCounts.fromJson(Map<String, dynamic> j) => TaskCounts(
        overdue: (j['overdue'] as num?)?.toInt() ?? 0,
        today: (j['today'] as num?)?.toInt() ?? 0,
        upcoming: (j['upcoming_14'] as num?)?.toInt() ?? 0,
        someday: (j['someday'] as num?)?.toInt() ?? 0,
        doneWeek: (j['done_week'] as num?)?.toInt() ?? 0,
      );

  final int overdue, today, upcoming, someday, doneWeek;

  /// The one Today number: overdue plus due today.
  int get todayTotal => overdue + today;
}

class ProjectRef {
  const ProjectRef({required this.id, required this.name, this.currency = ''});

  factory ProjectRef.fromJson(Map<String, dynamic> j) => ProjectRef(
        id: j['id'] as String,
        name: j['name'] as String? ?? '',
        currency: j['currency'] as String? ?? '',
      );

  final String id;
  final String name;
  final String currency;
}

class TaskComment {
  const TaskComment({
    required this.id,
    required this.author,
    required this.body,
    required this.createdAt,
    this.stepId,
    this.editedAt,
    this.tainted = false,
  });

  factory TaskComment.fromJson(Map<String, dynamic> j) => TaskComment(
        id: j['id'] as String,
        author: j['author'] as String? ?? '',
        body: j['body'] as String? ?? '',
        createdAt: j['created_at'] as String? ?? '',
        stepId: j['step_id'] as String?,
        editedAt: j['edited_at'] as String?,
        tainted: j['tainted'] == true,
      );

  final String id, author, body, createdAt;
  final String? stepId, editedAt;
  final bool tainted;

  /// The user's own comments are authored `user`; a bot's carry its id.
  bool get isMine => author == 'user';
}

/// What `POST /api/tasks/parse` read from a quick line.
class QuickReading {
  const QuickReading(this.json);

  final Map<String, dynamic> json;

  String get title => json['title'] as String? ?? '';
  bool get ready => json['ready'] == true;
  String? get dueText => json['due_text'] as String?;
  String? get reminderText => json['reminder_text'] as String?;
  String? get priority => json['priority'] as String?;
  String? get projectName => (json['project'] as Map?)?['name'] as String?;
  String? get budget => json['budget'] as String?;
  bool get starred => json['starred'] == true;
  int? get estimateMinutes => (json['estimate_minutes'] as num?)?.toInt();
  String? get repeatText => json['repeat_text'] as String?;
  String? get assigneeName => (json['assignee'] as Map?)?['name'] as String?;
  List<String> get tags =>
      [for (final t in (json['tags'] as List? ?? const [])) '$t'];

  String? get projectWords => json['project_words'] as String?;
  String? get budgetWords => json['budget_words'] as String?;
  String? get repeatWords => json['repeat_words'] as String?;
  String? get reminderWords => json['reminder_words'] as String?;
  String? get assigneeWords => json['assignee_words'] as String?;

  ({String id, String name})? get assignee {
    final a = json['assignee'];
    if (a is! Map) return null;
    return (id: '${a['id']}', name: '${a['name']}');
  }

  List<String> get warnings =>
      [for (final w in (json['warnings'] as List? ?? const [])) '$w'];

  /// The typed words each chip came from (`{"priority": ["!high"]}`).
  Map<String, List<String>> get matches {
    final m = json['matches'];
    if (m is! Map) return const {};
    return {
      for (final e in m.entries)
        '${e.key}': [for (final w in (e.value as List? ?? const [])) '$w'],
    };
  }

  /// Why it cannot be added yet, in the server's words; a bot waits for
  /// your confirm ([confirmedBot] is the bot id you confirmed).
  String? blockerFor(String? confirmedBot) {
    if (!ready) {
      for (final k in const [
        'project_question',
        'budget_problem',
        'repeat_problem',
        'assignee_question',
      ]) {
        final v = json[k];
        if (v is String && v.isNotEmpty) return v;
      }
      return 'Give the task a title.';
    }
    final bot = assignee;
    if (bot != null && bot.id != confirmedBot) {
      return 'Confirm handing this to ${bot.name} first.';
    }
    return null;
  }

  /// The body for `POST /api/tasks`: exactly what the server read. A bot is
  /// handed the task only once you confirmed it ([confirmedBot]).
  Map<String, dynamic> toTaskIn([String? confirmedBot]) {
    final project = json['project'] as Map?;
    final bot = assignee;
    return {
      'title': title,
      if (json['due_date'] != null) 'due_date': json['due_date'],
      if (json['priority'] != null) 'priority': json['priority'],
      if (project != null) 'project_id': project['id'],
      // In no project the budget counts in General's currency (owner, 2026-10-26).
      if (json['budget'] != null) 'allocated_budget': json['budget'],
      if (tags.isNotEmpty) 'tags': tags,
      if (starred) 'starred': true,
      if (estimateMinutes != null) 'estimate_minutes': estimateMinutes,
      if (json['reminder_at'] != null) 'reminder_at': json['reminder_at'],
      if (json['recurring'] != null) 'recurring': json['recurring'],
      if (json['recurring'] != null && json['recur_until'] != null)
        'recur_until': json['recur_until'],
      if (bot != null && bot.id == confirmedBot) ...{
        'assign_bot_id': bot.id,
        'assign_confirmed': true,
      },
    };
  }
}
