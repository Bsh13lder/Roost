import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../api/models.dart';
import '../../theme/tokens.dart';
import '../bot_markdown.dart';
import 'card_base.dart';
import 'reminder_card.dart';
import 'report_foot.dart';
import '../../voice/voice_widgets.dart';

export 'report_foot.dart' show reminderFoot;

const _routineFallback = 'Routine'; // an older Report kept no routine name
const _routineSources = {'routine', 'day_summary'};

/// A Report (owner, 2026-10-26: "like Grok"): a routine's result or a task's
/// reminder, drawn as the bot's own message: its text as markdown, no
/// headline, no card, and a quiet footer, "↻ Morning news · Run log ›" or
/// "🔔 Reminder". A single task's reminder adds four small chips.
class ReportBubble extends StatelessWidget {
  const ReportBubble({super.key, required this.message});
  final Message message;

  @override
  Widget build(BuildContext context) {
    final d = decodeBody(message.body);
    final headline = str(d?['headline']);
    if (d == null || headline.isEmpty) return QuietLine(message.body);
    final text = str(d['text']);
    final tainted = d['tainted'] == true || message.tainted;
    final reminder = d['source'] == 'reminder';
    final taskId = d['task_id'];
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          Tokens.space4, Tokens.space1, Tokens.space8, Tokens.space1),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        BotMarkdown(text.isEmpty ? headline : text),
        const SizedBox(height: Tokens.space1),
        Row(children: [
          Flexible(
            child: reminder && taskId is String
                ? ReminderChips(
                    message: message, taskId: taskId, tainted: tainted)
                : ReportFoot(
            label: reminder ? reminderFoot : _routineLabel(d),
            tainted: tainted,
            links: [
              if (!reminder && str(d['routine_id']).isNotEmpty)
                FootLink('Run log ›',
                    semantics: 'Open run log', onTap: () => _openLog(context, d)),
            ],
          ),
          ),
          SpeakButton(threadId: message.threadId, messageId: message.id),
        ]),
      ]),
    );
  }

  String? _routineLabel(Json d) {
    if (str(d['routine_id']).isEmpty && !_routineSources.contains(d['source'])) {
      return null;
    }
    final name = str(d['routine_name']);
    return '↻ ${name.isEmpty ? _routineFallback : name}';
  }

  void _openLog(BuildContext context, Json d) {
    final bot = str(d['bot_id']).isNotEmpty ? str(d['bot_id']) : (message.authorBotId ?? '');
    if (bot.isEmpty) return;
    context.push('/bots/$bot/routines/${str(d['routine_id'])}/log');
  }
}

