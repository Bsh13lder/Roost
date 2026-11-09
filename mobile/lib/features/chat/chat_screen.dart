import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/models.dart';
import '../../live/live_connection.dart';
import '../../nav/main_back.dart';
import '../../notify/notify_providers.dart';
import '../../theme/tokens.dart';
import '../../widgets/lensbot.dart';
import '../../chat/cards/approval_answers.dart';
import '../../chat/mentions.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_repo.dart';
import '../../chat/chat_menu.dart';
import '../../chat/message_actions.dart';
import '../../chat/reactions.dart';
import '../../profile/profile_screen.dart' show openProfile;
import '../../call/call_mic.dart';
import '../../call/call_screen.dart';
import 'chat_controller.dart';
import 'composer.dart';
import 'activity_pill.dart';
import 'chat_flow.dart';
import 'computer_steps.dart';
import 'run_steps.dart';
import 'message_view.dart';
import 'spoken_fix_strip.dart';
import '../../voice/audio_ports.dart';
import '../../voice/mic_controller.dart';
import '../../voice/voice_models.dart';
import '../../voice/read_aloud.dart';
import '../../voice/speech_controller.dart';
import '../../voice/voice_api.dart';
import '../../voice/voice_widgets.dart';
import '../../media/attachments.dart';
import '../../media/media_tray.dart';

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key, required this.botId});

  final String botId;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _text = TextEditingController();
  final _scroll = ScrollController();
  Message? _replyTo;
  bool _awayFromEnd = false;
  late final MicController _mic;
  late final SpeechController _speech;
  final Set<String> _readAloud = {};

  bool _hadText = false;

  /// The box's text right after a dictation filled it, while the box holds
  /// only dictated words; any keystroke since clears it (contract 2).
  String? _dictated;

  /// Voice tuning D3: the box as the ear filled it (the raw words), whether
  /// the check came back, the fixes shown now, and the correction on screen.
  String? _heard;
  bool _checked = false;
  List<SpeechFix> _fixes = const [];
  SpokenCorrection? _correction;

  @override
  void initState() {
    super.initState();
    _text.addListener(_textChanged);
    _scroll.addListener(_noteScroll);
    _openChat = ref.read(openChatProvider.notifier);
    _speech = ref.read(speechProvider.notifier);
    final voice = ref.read(voiceApiProvider);
    _mic = MicController(
      recorder: ref.read(voiceRecorderProvider),
      transcribe: (wav) => voice.transcribe(wav, botId: widget.botId),
      partial: (wav) => voice.partial(wav, botId: widget.botId),
      correct: (text) => voice.correct(text, widget.botId),
      correctOn: () =>
          ref.read(liveProvider).bots[widget.botId]?.voice.correctSpeech ?? false,
      onText: _dictatedText,
      onChecked: () => _checked = true,
      onCorrected: _corrected,
    )..addListener(() => setState(() {}));
    // Stay connected sends nothing about the chat you are reading.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _openChat.state = widget.botId;
    });
  }

  late final StateController<String?> _openChat;

  /// The composer emptied: ask again whether voice is there, so the Call
  /// button is right by the time it shows. Text that is not the dictation as
  /// it landed is typed text.
  void _textChanged() {
    final has = _text.text.isNotEmpty;
    if (_hadText && !has) ref.invalidate(voiceInfoProvider);
    _hadText = has;
    if (_dictated != null && _text.text != _dictated) _clearDictation();
    setState(() {});
  }

  void _clearDictation() {
    _dictated = null;
    _heard = null;
    _checked = false;
    _fixes = const [];
    _correction = null;
  }

  /// The Mac heard you: the words go after what is typed. The message counts
  /// as spoken only while every word in the box came from the voice service.
  void _dictatedText(String text) {
    final onlyDictated = _text.text.isEmpty || _text.text == _dictated;
    appendToComposer(_text, text);
    _dictated = onlyDictated ? _text.text : null;
    _heard = _dictated;
    _checked = false;
    _fixes = const [];
    _correction = null;
  }

  /// The check came back (voice tuning D3): the cleaned words take the raw
  /// ones' place while nobody edited them, with the fixes marked above.
  void _corrected(SpokenCorrection c) {
    final raw = _dictated;
    if (raw == null || _text.text != raw || !raw.endsWith(c.said)) return;
    final before = raw.substring(0, raw.length - c.said.length);
    final next = '$before${c.corrected}';
    // The dictation moves first: the box's listener sees the same words and keeps the bookkeeping.
    _dictated = next;
    _text.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: next.length),
    );
    setState(() {
      _checked = true;
      _fixes = c.fixes;
      _correction = c;
    });
  }

  /// Keep my words: the raw transcript back, the check still counted.
  void _keepMyWords() {
    final heard = _heard;
    if (heard == null) return;
    _dictated = heard;
    _text.value = TextEditingValue(
      text: heard,
      selection: TextSelection.collapsed(offset: heard.length),
    );
    setState(() {
      _fixes = const [];
      _correction = null;
    });
  }

  bool get _sendingSpoken => _dictated != null && _text.text == _dictated;

  /// Read replies aloud: a new reply of this bot plays by itself while this
  /// chat is open, on top and in the foreground.
  void _maybeReadAloud(ChatState? before, ChatState after) {
    final bot = ref.read(liveProvider).bots[widget.botId];
    final play = shouldReadAloud(
      readAloud: bot?.voice.readAloud ?? false,
      foreground: ref.read(appVisibleProvider),
      onTop: ModalRoute.of(context)?.isCurrent ?? true,
      loaded: before != null && !before.loading && after.threadId != null,
    );
    if (!play) return;
    final id = newReplyToRead(
        before: before?.messages ?? const [],
        after: after.messages,
        alreadyRead: _readAloud);
    if (id == null) return;
    _readAloud.add(id);
    _speech.speak(after.threadId!, id);
  }

  /// The list is reversed: offset 0 is the newest message.
  void _noteScroll() {
    final away = _scroll.hasClients && _scroll.offset > _ChatScreenState.chatJumpButtonAfter;
    if (away != _awayFromEnd) setState(() => _awayFromEnd = away);
  }

  String get _beforeCaret {
    final sel = _text.selection;
    final caret = sel.isValid ? sel.baseOffset : _text.text.length;
    return _text.text.substring(0, caret.clamp(0, _text.text.length));
  }

  /// "#word": your projects; otherwise "@word": your other bots.
  ({String trigger, List<MentionOption> options}) _mentions(LiveState live) {
    final projectQuery = mentionQuery(_beforeCaret, mentionProject);
    if (projectQuery != null) {
      final projects =
          ref.watch(taskProjectsProvider).valueOrNull ?? const <ProjectRef>[];
      return (
        trigger: mentionProject,
        options: matchingOptions(
            projectQuery, [for (final p in projects) MentionOption(p.id, p.name)]),
      );
    }
    return (
      trigger: mentionBot,
      options: matchingOptions(mentionQuery(_beforeCaret), [
        for (final b in live.bots.values)
          if (b.id != widget.botId) MentionOption(b.id, b.name),
      ]),
    );
  }

  void _pickMention(MentionOption o, String trigger) {
    final sel = _text.selection;
    final caret = sel.isValid ? sel.baseOffset : _text.text.length;
    final next = insertMention(_text.text, caret, o.name, trigger);
    _text.value = TextEditingValue(
      text: next.text,
      selection: TextSelection.collapsed(offset: next.caret),
    );
  }

  @override
  void dispose() {
    if (_openChat.state == widget.botId) {
      final chat = _openChat;
      // Not during the frame that disposes this screen.
      Future.microtask(() => chat.state = null);
    }
    _mic.dispose();
    if (_speech.busy) Future.microtask(_speech.stop);
    _text.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _send() {
    final value = _text.text;
    final tray = ref.read(trayProvider(widget.botId));
    if (!tray.isEmpty) {
      if (!tray.busy) _sendWithMedia(value);
      return;
    }
    if (value.trim().isEmpty) return;
    final spoken = _sendingSpoken;
    final heard = spoken && _checked ? _heard : null;
    final fixes = _fixes;
    _text.clear();
    _mic.clearError();
    final reply = _replyTo;
    setState(() {
      _replyTo = null;
      _clearDictation();
    });
    // A failure shows as the chat's error line; nothing waits on it here.
    ref
        .read(chatProvider(widget.botId).notifier)
        .send(value, replyTo: reply?.id, spoken: spoken, heard: heard, fixes: fixes)
        .ignore();
    _toEnd(animate: true);
  }

  /// Pictures first: upload them, then send your words with them. A failed
  /// upload keeps the pictures and the words, and says why; Send retries.
  Future<void> _sendWithMedia(String value) async {
    final chat = ref.read(chatProvider(widget.botId).notifier);
    final threadId = ref.read(chatProvider(widget.botId)).threadId;
    if (threadId == null) return;
    final media = await ref.read(trayProvider(widget.botId).notifier).upload(threadId);
    if (media == null || !mounted) return;
    final reply = _replyTo;
    try {
      await chat.send(value, replyTo: reply?.id, media: media);
    } catch (_) {
      return; // the chat's error line says why; the pictures stay for Send
    }
    if (!mounted) return;
    ref.read(trayProvider(widget.botId).notifier).clear();
    if (_text.text == value) _text.clear();
    setState(() => _replyTo = null);
    _toEnd(animate: true);
  }

  /// The newest message, at the bottom (offset 0 of the reversed list).
  void _toEnd({bool animate = false}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      if (animate) {
        _scroll.animateTo(0,
            duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      } else {
        _scroll.jumpTo(0);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final chat = ref.watch(chatProvider(widget.botId));
    final live = ref.watch(liveProvider);
    final bot = live.bots[widget.botId];
    ref.listen<ChatState>(chatProvider(widget.botId), _maybeReadAloud);
    // Back in front: voice may have come up (or gone) meanwhile.
    ref.listen<bool>(appVisibleProvider, (was, now) {
      if (now && was == false) ref.invalidate(voiceInfoProvider);
    });
    // A reversed list keeps the newest message in view by itself; reading
    // older messages is never pulled away.
    return Scaffold(
      appBar: _header(bot, chat),
      body: SpeechErrors(child: Column(
        children: [
          Expanded(
            child: Stack(children: [
              Positioned.fill(child: _messages(chat)),
              if (_awayFromEnd)
                Positioned(
                  right: Tokens.space3,
                  bottom: Tokens.space3,
                  child: _JumpToEnd(onTap: () => _toEnd(animate: true)),
                ),
            ]),
          ),
          if (chat.notice != null) _Notice(chat.notice!),
          if (chat.error != null && !chat.loading) _Notice(chat.error!, bad: true),
          if (_mic.error != null) _Notice(_mic.error!, bad: true),
          if (_replyTo != null)
            ReplyChip(
                quote: quotePreview(quoteSource(_replyTo!)),
                onCancel: () => setState(() => _replyTo = null)),
          _mentionList(live),
          MediaTray(botId: widget.botId),
          if (_correction != null)
            SpokenFixStrip(correction: _correction!, onKeep: _keepMyWords),
          _composer(bot),
        ],
      )),
    );
  }

  Widget _mentionList(LiveState live) {
    final open = _mentions(live);
    return MentionList(
        options: open.options,
        trigger: open.trigger,
        onPick: (o) => _pickMention(o, open.trigger));
  }

  PreferredSizeWidget _header(Bot? bot, ChatState chat) {
    return AppBar(
      backgroundColor: Tokens.bg,
      titleSpacing: 0,
      // Always an arrow to Home, even when the chat is the only page.
      leading: BackButton(onPressed: () => goBack(context)),
      actions: [
        ChatMenu(
          botId: widget.botId,
          bot: bot,
          threadId: chat.threadId,
          messages: chat.messages,
        ),
      ],
      title: InkWell(
        onTap: bot == null ? null : () => openProfile(context, bot.id),
        child: Row(
        children: [
          if (bot != null)
            LensbotAvatar(avatar: bot.avatar, size: 36, star: bot.isPrimary),
          const SizedBox(width: Tokens.space2),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(bot?.name ?? 'Chat',
                    style: const TextStyle(fontSize: Tokens.fsLead)),
                if (bot != null)
                  Text(statusLabel(bot.status),
                      style: const TextStyle(
                          fontSize: Tokens.fsCaption,
                          color: Tokens.textSecondary)),
              ],
            ),
          ),
        ],
        ),
      ),
    );
  }

  Widget _messages(ChatState chat) {
    if (chat.loading) return const Center(child: CircularProgressIndicator());
    if (chat.threadId == null) {
      return Center(
        child: TextButton(
          onPressed: () => ref.read(chatProvider(widget.botId).notifier).load(),
          child: Text('${chat.error ?? "Could not open this chat."} Try again'),
        ),
      );
    }
    final shown = [
      for (final m in chat.messages)
        if (!_emptyPlaceholder(m, chat)) m,
    ];
    final answers = pairCardAnswers(chat.messages);
    final reactions = foldReactions(chat.messages);
    final notifier = ref.read(chatProvider(widget.botId).notifier);
    final thread = chat.threadId;
    final computerRuns = ref.watch(computerRunsProvider)[thread] ?? const <ComputerRun>[];
    final bot = ref.watch(liveProvider).bots[widget.botId];
    final flow = buildChatFlow(
      messages: shown,
      answers: answers,
      runs: ref.watch(activityRunsProvider)[thread] ?? const [],
      computerRuns: computerRuns,
      streaming: chat.streaming,
      bot: bot,
    );
    final items = flow.items.reversed.toList();
    final canRead = _canReadAloud;
    final reading = ref.watch(speechProvider).key;
    return ListView.builder(
      controller: _scroll,
      reverse: true,
      padding: const EdgeInsets.symmetric(vertical: Tokens.space2),
      itemCount: items.length,
      itemBuilder: (_, i) {
        final item = items[i];
        if (item is ActivityItem) {
          return ActivityItemView(
            key: ValueKey('activity-${item.run.runId}'),
            item: item,
            avatar: bot?.avatar,
          );
        }
        if (item is LivePillItem) {
          return LiveBotPill(key: const ValueKey('activity-waiting'), bot: item.bot, words: item.words);
        }
        if (item is ComputerRun) {
          return computerRunTile(item);
        }
        final m = item as Message;
        return MessageView(
          message: m,
          text: flow.texts[m.id] ?? chat.streaming[m.id] ?? m.body,
          answers: answers,
          reaction: reactions[m.id],
          onReact: notifier.react,
          onReply: (target) => setState(() => _replyTo = target),
          onReadAloud: canRead && canSpeak(m)
              ? (target) => _speech.toggle(target.threadId, target.id)
              : null,
          reading: reading == m.id,
        );
      },
    );
  }

  static const chatJumpButtonAfter = 400.0;

  bool _emptyPlaceholder(Message m, ChatState chat) =>
      m.isPlaceholder && (chat.streaming[m.id] ?? m.body).isEmpty;

  bool get _canReadAloud =>
      ref.watch(voicePlayerProvider).supported &&
      ref.watch(voiceAvailableProvider);

  bool get _showMic =>
      _mic.phase != MicPhase.idle ||
      (ref.watch(voiceRecorderProvider).supported &&
          ref.watch(voiceAvailableProvider));

  /// Call needs the thread open: every turn is a message in it.
  bool get _canCall =>
      ref.watch(chatProvider(widget.botId)).threadId != null &&
      ref.watch(callMicProvider).supported &&
      ref.watch(voicePlayerProvider).supported &&
      ref.watch(voiceAvailableProvider);

  Widget _composer(Bot? bot) => ChatComposer(
        botId: widget.botId,
        bot: bot,
        text: _text,
        mic: _mic,
        showMic: _showMic,
        canCall: _canCall,
        onSend: _send,
        onStop: () => ref.read(chatProvider(widget.botId).notifier).stop(),
        onCall: () {
          if (_speech.busy) _speech.stop();
          openCall(context, widget.botId);
        },
      );
}

class _Notice extends StatelessWidget {
  const _Notice(this.text, {this.bad = false});
  final String text;
  final bool bad;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: Tokens.space4, vertical: Tokens.space1),
        child: Align(
          alignment: Alignment.centerLeft,
          child: Text(text,
              style: TextStyle(
                  color: bad ? Tokens.dangerText : Tokens.textFaint,
                  fontSize: Tokens.fsLabel)),
        ),
      );
}


/// The round ↓ that brings you back to the newest message.
class _JumpToEnd extends StatelessWidget {
  const _JumpToEnd({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        key: const Key('jump-to-end'),
        color: Tokens.panel,
        shape: const CircleBorder(side: BorderSide(color: Tokens.border)),
        elevation: 2,
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: const SizedBox(
            width: 40,
            height: 40,
            child: Icon(Icons.keyboard_arrow_down, color: Tokens.text),
          ),
        ),
      );
}
