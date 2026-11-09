import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../chat/cards/english_fix_card.dart';
import '../features/chat/chat_controller.dart';
import '../live/live_connection.dart';
import '../profile/bot_detail.dart';
import '../theme/tokens.dart';
import '../voice/speech_controller.dart';
import '../voice/voice_api.dart';
import '../voice/voice_models.dart';
import '../widgets/lensbot.dart';
import 'call_caption.dart';
import 'call_controller.dart';
import 'call_mic.dart';
import 'call_orb.dart';
import 'call_platform.dart';

/// Opens a voice call with [botId] over the chat.
Future<void> openCall(BuildContext context, String botId) => Navigator.of(context).push(
      MaterialPageRoute<void>(fullscreenDialog: true, builder: (_) => CallScreen(botId: botId)),
    );

/// The call: the bot's robot in a living orb, one word for what is happening,
/// what you said and what it is saying, then Mute, Speaker and End. Every
/// turn is an ordinary message in the bot's chat. The screen stays on; the
/// app going behind mutes the call until it is back.
class CallScreen extends ConsumerStatefulWidget {
  const CallScreen({super.key, required this.botId});

  final String botId;

  @override
  ConsumerState<CallScreen> createState() => _CallScreenState();
}

class _CallScreenState extends ConsumerState<CallScreen> with WidgetsBindingObserver {
  late final CallController _call;
  late final SpeechController _speech;
  late final KeepScreenOn _keepScreenOn;
  late final Speakerphone _speakerphone;
  bool _leaving = false;
  bool _speaker = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _speech = ref.read(speechProvider.notifier);
    _keepScreenOn = ref.read(keepScreenOnProvider);
    _speakerphone = ref.read(speakerphoneProvider);
    _call = _makeCall()..addListener(_changed);
    _call.chatChanged(ref.read(chatProvider(widget.botId)).messages, _status());
    unawaited(_keepScreenOn(true));
    unawaited(_speakerphone(true));
    _call.start();
  }

  CallController _makeCall() {
    final api = ref.read(voiceApiProvider);
    final threadId = ref.read(chatProvider(widget.botId)).threadId;
    final bot = ref.read(liveProvider).bots[widget.botId];
    return CallController(
      mic: ref.read(callMicProvider),
      warm: () => api.warm(botId: widget.botId),
      transcribe: api.transcribe,
      // Every turn is your spoken words as the Mac heard them (contract 2).
      send: (text) => ref.read(chatProvider(widget.botId).notifier).send(text, call: true, spoken: true),
      speak: (m) => _speech.speak(m.threadId, m.id),
      speakLive: _speech.speakLive,
      // The bot's speed as it is now: a change mid-call (its own set_my_voice,
      // the Info tab) reaches the next line through the live bot.
      speakLine: (key) => _speech.speakLine(widget.botId, key, speed: _speed),
      stopSpeaking: _speech.stop,
      beat: ({String? interrupted}) async {
        if (threadId != null) await api.callBeat(threadId, interrupted: interrupted);
      },
      endCall: () async {
        if (threadId != null) await api.callEnd(threadId);
      },
      frames: ref.read(frameBusProvider).stream,
      liveSpeech: api.liveSpeech,
      botName: bot?.name ?? 'Your bot',
    );
  }

  void _changed() {
    if (!mounted) return;
    if (_call.phase == CallPhase.ended && !_leaving) {
      // A goodbye word ended the call: back to the chat.
      _leaving = true;
      Navigator.of(context).pop();
      return;
    }
    setState(() {});
  }

  BotStatus? _status() => ref.read(liveProvider).bots[widget.botId]?.status;

  /// The bot's detail is fetched again on every `bot_updated`; the live bot
  /// stands in until it has loaded.
  double get _speed =>
      ref.read(botDetailProvider(widget.botId)).valueOrNull?.voice.speed ??
      ref.read(liveProvider).bots[widget.botId]?.voice.speed ??
      defaultSpeed;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused || AppLifecycleState.hidden:
        _call.pause();
      case AppLifecycleState.resumed:
        _call.resume();
      default:
        return;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _call.removeListener(_changed);
    unawaited(_keepScreenOn(false));
    unawaited(_call.end().whenComplete(_call.dispose));
    super.dispose();
  }

  /// Leaves at once; the call winds down (mic, playback) behind it.
  void _hangUp() {
    _leaving = true;
    unawaited(_call.end());
    Navigator.of(context).pop();
  }

  void _toggleSpeaker() {
    setState(() => _speaker = !_speaker);
    unawaited(_speakerphone(_speaker));
  }

  void _chatChanged(ChatState chat, Bot? bot) =>
      _call.chatChanged(chat.messages, bot?.status, activity: bot?.activity, streaming: chat.streaming);

  @override
  Widget build(BuildContext context) {
    ref.listen<ChatState>(chatProvider(widget.botId), (_, chat) => _chatChanged(chat, ref.read(liveProvider).bots[widget.botId]));
    ref.listen<LiveState>(liveProvider, (_, live) => _chatChanged(ref.read(chatProvider(widget.botId)), live.bots[widget.botId]));
    ref.listen<SpeechState>(speechProvider, (_, s) {
      if (s.error != null) _call.speechFailed(s.error!);
    });
    final bot = ref.watch(liveProvider).bots[widget.botId];
    return Scaffold(
      key: const Key('call-screen'),
      backgroundColor: Tokens.bg,
      body: SafeArea(
        child: Column(children: [
          _top(bot),
          const Spacer(),
          GestureDetector(
            key: const Key('call-orb'),
            onTap: _call.orbTapped,
            child: CallOrb(
              phase: _call.phase,
              level: _call.level,
              child: bot == null ? const SizedBox.shrink() : LensbotAvatar(avatar: bot.avatar, size: 88, status: bot.status),
            ),
          ),
          const SizedBox(height: Tokens.space6),
          Text(callStatusWord(_call, bot?.name ?? 'Your bot'),
              key: const Key('call-status'),
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: Tokens.fsHeading, color: Tokens.text)),
          const SizedBox(height: Tokens.space3),
          _captions(),
          const Spacer(),
          _buttons(),
        ]),
      ),
    );
  }

  Widget _top(Bot? bot) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space2, vertical: Tokens.space2),
        child: Row(children: [
          IconButton(
            tooltip: 'Back to the chat',
            icon: const Icon(Icons.keyboard_arrow_down_rounded, size: 28),
            onPressed: _hangUp,
          ),
          Expanded(
            child: Text(bot?.name ?? '',
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: Tokens.fsLead, color: Tokens.textSecondary)),
          ),
          const SizedBox(width: 48),
        ]),
      );

  bool get _showSaying =>
      _call.saying != null && (_call.phase == CallPhase.speaking || _call.phase == CallPhase.thinking);

  Widget _captions() {
    final fix = _call.heardFix;
    final lines = <Widget>[
      if (fix != null)
        EnglishFixText(fix,
            key: const Key('call-heard-fix'), textAlign: TextAlign.center, baseColor: Tokens.textFaint)
      else if (_call.heard != null)
        Text('“${_call.heard}”',
            key: const Key('call-heard'),
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsBody)),
      if (_showSaying)
        Text(_call.saying!,
            key: const Key('call-saying'),
            textAlign: TextAlign.center,
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsRow)),
      if (_call.note != null)
        Text(_call.note!,
            key: const Key('call-note'),
            textAlign: TextAlign.center,
            style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Tokens.space8),
      child: Column(children: [
        for (final l in lines) Padding(padding: const EdgeInsets.only(bottom: Tokens.space2), child: l),
      ]),
    );
  }

  Widget _buttons() => Padding(
        padding: const EdgeInsets.only(bottom: Tokens.space8),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
          _RoundButton(
            key: const Key('call-mute'),
            label: _call.muted ? 'Unmute' : 'Mute',
            icon: _call.muted ? Icons.mic_off_rounded : Icons.mic_none_rounded,
            color: _call.muted ? Tokens.text : Tokens.raised,
            iconColor: _call.muted ? Tokens.bg : Tokens.text,
            onTap: _call.phase == CallPhase.off ? null : _call.toggleMute,
          ),
          _RoundButton(
            key: const Key('call-speaker'),
            label: 'Speaker',
            icon: _speaker ? Icons.volume_up_rounded : Icons.volume_down_rounded,
            color: _speaker ? Tokens.text : Tokens.raised,
            iconColor: _speaker ? Tokens.bg : Tokens.text,
            onTap: _toggleSpeaker,
          ),
          _RoundButton(
            key: const Key('call-end'),
            label: 'End',
            icon: Icons.call_end_rounded,
            color: Tokens.callEnd,
            iconColor: Tokens.onAccent,
            onTap: _hangUp,
          ),
        ]),
      );
}

/// The one word under the orb.
String callStatusWord(CallController call, String botName) {
  if (call.muted && call.phase == CallPhase.listening) return 'Muted';
  return switch (call.phase) {
    CallPhase.warming => 'Starting…',
    CallPhase.listening => 'Listening',
    CallPhase.hearing => 'Hearing you…',
    CallPhase.thinking => thinkingWord(call.activity),
    CallPhase.speaking => 'Speaking',
    CallPhase.asking => '$botName is asking you. Say yes or no, or answer in the chat.',
    CallPhase.off => call.error ?? 'The call could not start.',
    CallPhase.ended => 'Call ended',
  };
}

class _RoundButton extends StatelessWidget {
  const _RoundButton({
    super.key,
    required this.label,
    required this.icon,
    required this.color,
    required this.iconColor,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final Color color;
  final Color iconColor;
  final VoidCallback? onTap;

  static const size = 64.0;

  @override
  Widget build(BuildContext context) => Column(mainAxisSize: MainAxisSize.min, children: [
        Material(
          color: color,
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox.square(dimension: size, child: Icon(icon, color: iconColor, size: 28)),
          ),
        ),
        const SizedBox(height: Tokens.space2),
        Text(label, style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
      ]);
}
