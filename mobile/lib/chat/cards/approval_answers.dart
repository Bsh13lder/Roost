import '../../api/models.dart';
import 'card_base.dart';

/// An "approval" message's body: the card id, its kind and step titles.
class ApprovalRef {
  const ApprovalRef(this.cardId, this.kind, this.steps);
  final String cardId;
  final String kind; // "ask" or "plan"
  final List<String> steps;
}

ApprovalRef? parseApprovalMessage(String body) {
  final d = decodeBody(body);
  if (d == null || d['card_id'] is! String) return null;
  final steps = d['steps'] is List
      ? [for (final s in d['steps'] as List) if (s is String) s]
      : <String>[];
  return ApprovalRef(
      d['card_id'] as String, d['kind'] == 'plan' ? 'plan' : 'ask', steps);
}

/// Each card's answer words, by card id: the `card_answer` line you posted
/// after an approval message and before the next one (web `pairCardAnswers`).
Map<String, String> pairCardAnswers(List<Message> messages) {
  final lines = <String, String>{};
  ApprovalRef? waiting;
  for (final m in messages) {
    if (m.kind == 'approval') {
      waiting = parseApprovalMessage(m.body);
    } else if (m.kind == 'card_answer' && waiting != null) {
      lines[waiting.cardId] = m.body;
      waiting = null;
    }
  }
  return lines;
}

const expiredLine = 'Replaced by a newer question.';
const failedLine = "It didn't run.";
const choiceAnsweredLine = 'You answered.';
const choiceDismissedLine = 'Dismissed: counts as No.';

/// A closed card as the one quiet line that replaces its buttons.
String closedLine(Json card) {
  final state = str(card['state']);
  final steps = jsonList(card['steps']);
  final title = steps.isEmpty ? '' : str(steps.first['title']);
  if (state == 'expired') return expiredLine;
  if (state == 'failed') return failedLine;
  if (card['choice'] is Map) {
    return state == 'declined' ? choiceDismissedLine : choiceAnsweredLine;
  }
  if (card['kind'] == 'plan') {
    return switch (state) {
      'approved' => 'You accepted the proposal.',
      'edited' => 'You asked for changes to the proposal.',
      _ => 'You declined the proposal.',
    };
  }
  if (card['pay'] == true) {
    // The Pay card (owner, 2026-11-05): Pay · Don't pay.
    return state == 'approved' ? 'You paid: $title' : 'Not paid: $title';
  }
  if (card['send'] == true) {
    // The Send card (owner, 2026-11-03): Send · Don't send · Change it….
    return switch (state) {
      'approved' => 'Sent: $title',
      'edited' => 'You asked for a change: $title',
      _ => 'Not sent: $title',
    };
  }
  return state == 'approved' ? 'Yes: $title' : 'No: $title';
}
