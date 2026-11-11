import 'package:flutter/widgets.dart';

import '../../api/models.dart';
import 'approval_cards.dart';
import 'card_base.dart';
import 'created_bot_card.dart';
import 'english_fix_card.dart';
import 'key_card.dart';
import 'model_card.dart';
import 'note_lines.dart';
import 'proposal_cards.dart';
import 'report_bubble.dart';
import 'routine_finished_line.dart';
import 'stuck_card.dart';
import 'suggestion_card.dart';
import 'task_cards.dart';

/// The widget for a message kind that is a card or a special line, or null
/// when the message is an ordinary one (text, card_answer, notices).
/// [onReply] gives a Stuck card its Reply (quote it for your next message).
Widget? cardFor(Message m,
    {Map<String, String> answers = const {},
    void Function(Message message)? onReply}) {
  final key = ValueKey('card-${m.id}');
  switch (m.kind) {
    case 'approval':
      final id = decodeBody(m.body)?['card_id'];
      return ApprovalMessageCard(
          key: key, body: m.body, answer: id is String ? answers[id] : null);
    case 'stuck':
      return StuckMessageCard(
          key: key,
          body: m.body,
          tainted: m.tainted,
          onReply: onReply == null || m.seq == 0 ? null : () => onReply(m));
    case 'bot_created':
      return CreatedBotCard(key: key, body: m.body);
    case 'suggestion':
      return SuggestionCard(key: key, body: m.body, tainted: m.tainted);
    case 'model_suggestion':
      return ModelSuggestionCard(key: key, body: m.body, tainted: m.tainted);
    case 'skill_proposal':
      return SkillProposalCard(key: key, body: m.body);
    case 'instructions_proposal':
      return InstructionsProposalCard(key: key, body: m.body);
    case 'routine_proposal':
      return RoutineProposalCard(key: key, body: m.body);
    case 'connector_request':
      return KeyRequestCard(key: key, body: m.body);
    case 'report':
      // A Report is the bot's own bubble with a quiet footer (2026-10-26).
      final report = decodeBody(m.body);
      if (report?['headline'] is! String) return null;
      return ReportBubble(key: key, message: m);
    case 'task_cards':
      return TaskCardsCard(key: key, message: m);
    case 'memory_note':
      return MemoryNoteLine(key: key, message: m);
    case 'fresh_start':
      return QuietLine(m.body, key: key);
    case 'english_fix':
      return EnglishFixCard(key: key, message: m);
    case 'memory_offer':
      return MemoryOfferLine(key: key, message: m);
    case 'mac_activity':
      return MacActivityLine(key: key, message: m);
    case 'program_activity':
      return ProgramActivityLine(key: key, body: m.body);
    case 'routine_note':
    case 'question_note':
      final line = decodeBody(m.body)?['text'];
      return line is String ? QuietLine(line, key: key) : null;
    case 'routine_finished':
      return RoutineFinishedLine(key: key, message: m);
    case 'handoff':
      return QuietLine('⇄ ${m.body}', key: key);
    case 'approval_result':
      return const SizedBox.shrink();
  }
  return null;
}
