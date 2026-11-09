import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/tokens.dart';
import 'audio_ports.dart';
import 'mic_controller.dart';
import 'speech_controller.dart';
import 'voice_api.dart';
import 'voice_models.dart';

/// The composer's mic: a mic while idle, a stop square while recording, a
/// small spinner while the Mac listens.
class MicButton extends StatelessWidget {
  const MicButton({super.key, required this.mic});

  final MicController mic;

  @override
  Widget build(BuildContext context) {
    return switch (mic.phase) {
      MicPhase.idle => IconButton(
        key: const Key('mic'),
        tooltip: 'Speak',
        icon: const Icon(Icons.mic_none_rounded),
        onPressed: mic.start,
      ),
      MicPhase.recording => IconButton.filled(
        key: const Key('mic-stop'),
        tooltip: 'Stop recording',
        icon: const Icon(Icons.stop_rounded),
        onPressed: mic.finish,
      ),
      MicPhase.listening || MicPhase.checking => const Padding(
        padding: EdgeInsets.all(Tokens.space3),
        child: SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      ),
    };
  }
}

/// Takes the text box's place while recording or listening: a pulsing dot
/// and the seconds, with Cancel, and the words heard so far as they come
/// (voice tuning D4); then "Listening…", then "Checking…".
class RecordingStrip extends StatelessWidget {
  const RecordingStrip({super.key, required this.mic, this.flat = false});

  final MicController mic;

  /// Inside the composer pill: no box of its own.
  final bool flat;

  /// The live words grow to this many lines, then scroll with the newest in view.
  static const liveMaxLines = 4;
  static const _liveLineHeight = 1.35;

  @override
  Widget build(BuildContext context) {
    final listening = mic.phase == MicPhase.listening || mic.phase == MicPhase.checking;
    final live = listening ? '' : mic.live;
    return Container(
      key: const Key('recording-strip'),
      constraints: BoxConstraints(minHeight: flat ? 40 : 48),
      padding: const EdgeInsets.symmetric(horizontal: Tokens.space2),
      decoration: flat
          ? null
          : BoxDecoration(
              color: Tokens.raised,
              borderRadius: BorderRadius.circular(Tokens.radiusLg),
            ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (live.isNotEmpty) _liveWords(live),
          SizedBox(height: flat ? 40 : 48, child: Row(children: _controls(listening, live.isEmpty))),
        ],
      ),
    );
  }

  /// What the ear heard so far, whole, at the composer's size: it grows to
  /// [liveMaxLines] and then keeps the newest words in view.
  Widget _liveWords(String live) => Padding(
        padding: const EdgeInsets.fromLTRB(Tokens.space2, Tokens.space2, Tokens.space1, 0),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: Tokens.fsLead * _liveLineHeight * liveMaxLines),
          child: SingleChildScrollView(
            reverse: true,
            child: Text(
              live,
              key: const Key('mic-live'),
              style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLead, height: _liveLineHeight),
            ),
          ),
        ),
      );

  List<Widget> _controls(bool listening, bool noWordsYet) => [
        if (listening)
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(left: Tokens.space2),
              child: Text(
                mic.phase == MicPhase.checking ? 'Checking…' : 'Listening…',
                key: const Key('mic-wait'),
                style: const TextStyle(color: Tokens.textSecondary),
              ),
            ),
          )
        else ...[
          IconButton(
            key: const Key('mic-cancel'),
            tooltip: 'Cancel recording',
            iconSize: 20,
            icon: const Icon(Icons.close_rounded),
            onPressed: mic.cancel,
          ),
          const _PulsingDot(),
          const SizedBox(width: Tokens.space2),
          Text(
            recordingClock(mic.seconds),
            key: const Key('mic-seconds'),
            style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()]),
          ),
          const SizedBox(width: Tokens.space2),
          if (noWordsYet)
            const Expanded(
              child: Text(
                'Recording · tap stop when done',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsLabel),
              ),
            ),
        ],
      ];
}

class _PulsingDot extends StatefulWidget {
  const _PulsingDot();

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
    opacity: Tween(begin: 0.35, end: 1.0).animate(_pulse),
    child: Container(
      key: const Key('mic-dot'),
      width: 10,
      height: 10,
      decoration: const BoxDecoration(
        color: Tokens.dangerText,
        shape: BoxShape.circle,
      ),
    ),
  );
}

/// The small speaker under a bot reply or a Report: tap to hear it, tap again
/// to stop. Hidden while voice isn't running or this build can't play.
class SpeakButton extends ConsumerWidget {
  const SpeakButton({
    super.key,
    required this.threadId,
    required this.messageId,
  });

  final String threadId;
  final String messageId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!ref.watch(voicePlayerProvider).supported ||
        !ref.watch(voiceAvailableProvider) ||
        threadId.isEmpty) {
      return const SizedBox.shrink();
    }
    final speech = ref.watch(speechProvider);
    final mine = speech.key == messageId;
    return SizedBox(
      width: 28,
      height: 28,
      child: IconButton(
        key: Key('speak-$messageId'),
        padding: EdgeInsets.zero,
        iconSize: 18,
        tooltip: mine ? 'Stop reading' : 'Read aloud',
        color: mine ? Tokens.text : Tokens.textFaint,
        icon: mine && speech.loading
            ? const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(
                mine ? Icons.stop_circle_outlined : Icons.volume_up_outlined,
              ),
        onPressed: () =>
            ref.read(speechProvider.notifier).toggle(threadId, messageId),
      ),
    );
  }
}

/// Shows a failed read-aloud's words once, as a snack bar.
class SpeechErrors extends ConsumerWidget {
  const SpeechErrors({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen<SpeechState>(speechProvider, (_, next) {
      final error = next.error;
      if (error != null && ModalRoute.of(context)?.isCurrent != false) {
        ScaffoldMessenger.maybeOf(
          context,
        )?.showSnackBar(SnackBar(content: Text(error)));
      }
    });
    return child;
  }
}
