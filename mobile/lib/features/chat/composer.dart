import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/models.dart';
import '../../chat/chat_mode.dart';
import '../../chat/chat_mode_pill.dart';
import '../../profile/bot_detail.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../../voice/mic_controller.dart';
import '../../voice/voice_widgets.dart';
import '../../widgets/profile_kit.dart' show attempt;
import '../../media/attach_sheet.dart';
import '../../media/attachments.dart';
import '../../vault/save_password_sheet.dart';

/// The chat's composer: one round pill with + (pictures, a video, and the
/// computer's chat mode),
/// the text, the mic, and one round button on the right: Call while the box
/// is empty, Send once there is text, Stop while the bot works and the box is
/// empty.
class ChatComposer extends ConsumerWidget {
  const ChatComposer({
    super.key,
    required this.botId,
    required this.bot,
    required this.text,
    required this.mic,
    required this.showMic,
    required this.canCall,
    required this.onSend,
    required this.onStop,
    required this.onCall,
  });

  final String botId;
  final Bot? bot;
  final TextEditingController text;
  final MicController mic;
  final bool showMic;
  final bool canCall;
  final VoidCallback onSend;
  final VoidCallback onStop;
  final VoidCallback onCall;

  static const buttonSize = 40.0;
  static const pillRadius = 28.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final recording = mic.phase != MicPhase.idle;
    final name = bot?.name ?? ref.watch(botDetailProvider(botId)).valueOrNull?.name;
    return SafeArea(
      top: false,
      child: Container(
        key: const Key('composer-pill'),
        margin: const EdgeInsets.fromLTRB(Tokens.space3, Tokens.space1, Tokens.space3, Tokens.space2),
        padding: const EdgeInsets.all(Tokens.space1),
        decoration: BoxDecoration(
          color: Tokens.raised,
          borderRadius: BorderRadius.circular(pillRadius),
          border: Border.all(color: Tokens.border),
        ),
        child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          _PlusButton(botId: botId),
          Expanded(child: recording ? RecordingStrip(mic: mic, flat: true) : _field(name)),
          if (showMic) _round(child: MicButton(mic: mic)),
          const SizedBox(width: Tokens.space1),
          _action(context, hasMedia: !ref.watch(trayProvider(botId)).isEmpty),
        ]),
      ),
    );
  }

  Widget _field(String? name) => TextField(
        key: const Key('composer'),
        controller: text,
        minLines: 1,
        maxLines: 6,
        textInputAction: TextInputAction.newline,
        style: const TextStyle(fontSize: Tokens.fsLead),
        decoration: InputDecoration(
          hintText: name == null ? 'Message' : 'Ask $name',
          filled: false,
          border: InputBorder.none,
          enabledBorder: InputBorder.none,
          focusedBorder: InputBorder.none,
          isDense: true,
          contentPadding: const EdgeInsets.symmetric(horizontal: Tokens.space3, vertical: 10),
        ),
      );

  Widget _round({required Widget child}) => SizedBox.square(dimension: buttonSize, child: Center(child: child));

  Widget _action(BuildContext context, {required bool hasMedia}) {
    final accent = AccentColors.of(context).accent;
    final typed = text.text.trim().isNotEmpty || hasMedia;
    final working = bot?.status == BotStatus.onIt;
    final (Key key, String tip, IconData icon, VoidCallback tap, Color fill) = switch ((typed, working, canCall)) {
      (true, _, _) => (const Key('send'), 'Send', Icons.arrow_upward_rounded, onSend, accent),
      (false, true, _) => (const Key('stop'), 'Stop', Icons.stop_rounded, onStop, Tokens.text),
      (false, false, true) => (const Key('call'), 'Call ${bot?.name ?? ''}'.trim(), Icons.graphic_eq_rounded, onCall, accent),
      _ => (const Key('send'), 'Send', Icons.arrow_upward_rounded, onSend, Tokens.border),
    };
    return Tooltip(
      message: tip,
      child: Material(
        key: key,
        color: fill,
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: tap,
          child: SizedBox.square(
            dimension: buttonSize,
            child: Icon(icon, size: 22, color: switch (fill) {
              Tokens.text => Tokens.bg,
              Tokens.border => Tokens.textFaint,
              _ => Tokens.onAccent,
            }),
          ),
        ),
      ),
    );
  }
}

/// + inside the pill: a photo, the camera or a video for the bot to look at,
/// for a bot on its Linux computer how it uses it (Ask me · Just browse ·
/// Full auto), and Save a password.
class _PlusButton extends ConsumerWidget {
  const _PlusButton({required this.botId});

  final String botId;

  Future<void> _openMode(BuildContext context, WidgetRef ref, BotDetail bot) async {
    final current = chatModeOf(bot);
    final picked = await showModalBottomSheet<ChatMode>(
      context: context,
      backgroundColor: Tokens.panel,
      builder: (_) => ChatModeSheet(current: current, title: 'How ${bot.name} uses its computer'),
    );
    if (picked == null || picked == current || !context.mounted) return;
    await attempt(context, () => saveChatMode(ref, bot, picked));
  }

  Future<void> _open(BuildContext context, WidgetRef ref, BotDetail? bot) async {
    final linux = bot != null && bot.computer == 'linux';
    final choice = await showAttachSheet(context,
        computerLabel: linux ? chatModeLabel(chatModeOf(bot)) : null);
    if (choice == null || !context.mounted) return;
    if (choice == AttachChoice.computer) {
      if (linux) await _openMode(context, ref, bot);
      return;
    }
    if (choice == AttachChoice.password) {
      await showSavePasswordSheet(context);
      return;
    }
    await attach(ref, botId, choice);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bot = ref.watch(botDetailProvider(botId)).valueOrNull;
    return SizedBox.square(
      dimension: ChatComposer.buttonSize,
      child: IconButton(
        key: const Key('composer-plus'),
        tooltip: 'Add a picture',
        padding: EdgeInsets.zero,
        style: IconButton.styleFrom(backgroundColor: Tokens.panel),
        icon: const Icon(Icons.add_rounded, color: Tokens.textSecondary),
        onPressed: () => _open(context, ref, bot),
      ),
    );
  }
}
