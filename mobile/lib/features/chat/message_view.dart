import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/models.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../../chat/bot_markdown.dart';
import '../../chat/cards/card_router.dart';
import '../../chat/message_actions.dart';
import '../../chat/reactions.dart';
import '../../chat/mentions.dart';
import '../../chat/project_tokens.dart';
import '../../chat/web_mark.dart';
import '../../board/projects/project_page.dart';
import '../../board/tasks/task_repo.dart';
import '../../util/app_time.dart';
import '../../voice/voice_widgets.dart';
import '../../media/message_media.dart';

/// Kinds drawn as an ordinary chat message. Cards and special lines come from
/// `cardFor`; every other kind shows as one quiet line.
const _plainKinds = {'text'};

class MessageView extends StatelessWidget {
  const MessageView({
    super.key,
    required this.message,
    required this.text,
    this.answers = const {},
    this.reaction,
    this.onReact,
    this.onReply,
    this.onReadAloud,
    this.reading = false,
  });

  final Message message;

  /// The body, or the text streamed so far.
  final String text;

  /// Each approval card's answer words, by card id.
  final Map<String, String> answers;
  final String? reaction;
  final ReactCallback? onReact;
  final void Function(Message message)? onReply;

  /// Read aloud / Stop reading in the long-press menu (a bot reply, while
  /// voice runs); [reading] is true while this message plays.
  final void Function(Message message)? onReadAloud;
  final bool reading;

  @override
  Widget build(BuildContext context) {
    if (message.kind == 'reaction') return const SizedBox.shrink();
    final card = cardFor(message, answers: answers, onReply: onReply);
    if (card != null) return card;
    if (!_plainKinds.contains(message.kind) || message.role == 'activity') {
      return _QuietLine(_quietText(message, text));
    }
    final body = message.fromUser
        ? _UserBubble(message)
        : _BotReply(message, text);
    final tapback = reaction == null ? null : reactionGlyphs[reaction]?.glyph;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onLongPress: message.seq == 0
          ? null
          : () => showMessageActions(
              context,
              message: message,
              reaction: reaction,
              onReact: onReact,
              onReply: onReply,
              copyText: message.fromUser ? null : text,
              onReadAloud: onReadAloud,
              reading: reading,
            ),
      child: Column(
        crossAxisAlignment: message.fromUser
            ? CrossAxisAlignment.end
            : CrossAxisAlignment.start,
        children: [
          body,
          if (tapback != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
              child: Text(tapback, key: const Key('tapback')),
            ),
        ],
      ),
    );
  }
}

String _quietText(Message m, String text) {
  final body = text.trim();
  if (body.isNotEmpty && !body.startsWith('{') && !body.startsWith('[')) {
    return body;
  }
  return 'Open this on the web for now.';
}

class _QuietLine extends StatelessWidget {
  const _QuietLine(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(
      vertical: Tokens.space2,
      horizontal: Tokens.space6,
    ),
    child: Text(
      text,
      textAlign: TextAlign.center,
      style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsLabel),
    ),
  );
}

class _UserBubble extends ConsumerWidget {
  const _UserBubble(this.message);
  final Message message;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projects = [
      for (final p in ref.watch(taskProjectsProvider).valueOrNull ?? const [])
        MentionOption(p.id, p.name),
    ];
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.fromLTRB(
          Tokens.space8 * 2,
          Tokens.space1,
          Tokens.space3,
          Tokens.space1,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: Tokens.space3,
          vertical: Tokens.space2,
        ),
        decoration: BoxDecoration(
          color: Tokens.raised,
          borderRadius: BorderRadius.circular(Tokens.radiusLg),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            if (message.replyQuote != null)
              ReplyQuote(
                quote: message.replyQuote!,
                tainted: message.replyTainted,
              ),
            MessageMedia(media: message.media),
            if (message.body.trim().isNotEmpty) ProjectText(message.body, projects: projects),
            _Time(message.createdAt),
          ],
        ),
      ),
    );
  }
}

class _BotReply extends StatelessWidget {
  const _BotReply(this.message, this.text);
  final Message message;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        Tokens.space4,
        Tokens.space1,
        Tokens.space8,
        Tokens.space1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (message.replyQuote != null)
            ReplyQuote(
              quote: message.replyQuote!,
              tainted: message.replyTainted,
            ),
          // A screenshot the bot sent is Roost's own picture, never one a page linked.
          MessageMedia(media: message.media),
          // No raw HTML is drawn and no image is ever fetched.
          BotMarkdown(text),
          // The web mark sits quietly under the text, never above it.
          if (message.tainted && message.seq > 0) const WebMark(),
          if (message.seq > 0)
            Row(mainAxisSize: MainAxisSize.min, children: [
              _Time(message.createdAt),
              const SizedBox(width: Tokens.space1),
              SpeakButton(threadId: message.threadId, messageId: message.id),
            ]),
        ],
      ),
    );
  }
}

class _Time extends StatelessWidget {
  const _Time(this.iso);
  final String iso;

  @override
  Widget build(BuildContext context) {
    if (iso.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: Tokens.space1),
      child: Text(
        appClock(iso),
        style: const TextStyle(
          color: Tokens.textFaint,
          fontSize: Tokens.fsCaption,
        ),
      ),
    );
  }
}

/// Your own words, each "#Project Name" you picked drawn as a chip that opens
/// that project's page (2026-10-26); an unknown "#word" stays text.
class ProjectText extends StatelessWidget {
  const ProjectText(this.text, {super.key, required this.projects});
  final String text;
  final List<MentionOption> projects;

  @override
  Widget build(BuildContext context) {
    final parts = splitProjectTokens(text, projects);
    return Text.rich(
      TextSpan(
        children: [
          for (final p in parts)
            if (p.project == null)
              TextSpan(text: p.text)
            else
              WidgetSpan(
                alignment: PlaceholderAlignment.middle,
                child: _ProjectChip(project: p.project!),
              ),
        ],
      ),
      style: const TextStyle(fontSize: Tokens.fsLead),
    );
  }
}

class _ProjectChip extends StatelessWidget {
  const _ProjectChip({required this.project});
  final MentionOption project;

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    return Semantics(
      label: 'Project ${project.name}',
      button: true,
      excludeSemantics: true,
      child: GestureDetector(
        key: Key('project-chip-${project.id}'),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => ProjectPage(projectId: project.id),
          ),
        ),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
          decoration: BoxDecoration(
            color: accent.tint,
            borderRadius: BorderRadius.circular(Tokens.radiusSm),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.folder_outlined, size: 14, color: accent.soft),
              const SizedBox(width: 3),
              Text(
                project.name,
                style: TextStyle(
                  fontSize: Tokens.fsLead,
                  fontWeight: FontWeight.w600,
                  color: accent.soft,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
