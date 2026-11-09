import '../../api/api_error.dart';
import 'quick_draft.dart';
import 'task_models.dart';
import 'task_repo.dart';

const quickParseDelay = Duration(milliseconds: 350);

/// The longest quick line the server reads.
const maxQuickLine = 300;

/// Why a quick line could not be added, in the server's words.
class QuickAddProblem implements Exception {
  const QuickAddProblem(this.message);
  final String message;

  @override
  String toString() => message;
}

/// Reads [draft] once more and adds exactly what the server read now. Throws
/// [QuickAddProblem] when the reading is not ready or the add fails.
Future<TaskItem> addQuickLine(TaskRepo repo, QuickDraft draft) async {
  try {
    final reading = await repo.parseDraft(draft);
    final blocker = reading.blockerFor(draft.confirmedBot);
    if (blocker != null) throw QuickAddProblem(blocker);
    return await repo.create(draft.createBody(reading));
  } on ApiException catch (e) {
    throw QuickAddProblem(e.message);
  }
}
