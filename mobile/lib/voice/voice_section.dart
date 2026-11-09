import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../profile/bot_detail.dart';
import '../theme/accent.dart';
import '../widgets/grouped_card.dart';
import '../widgets/profile_kit.dart';
import 'audio_ports.dart';
import 'speech_controller.dart';
import 'voice_api.dart';
import 'voice_models.dart';

/// The words under the Correct what I say switch (voice tuning D3).
const correctSpeechHint =
    'Shows a corrected copy of what you say, in any language, with the '
    'mistakes marked: names, numbers, sites and grammar.';

/// The Voice card on a bot's Settings (beside Model & effort): Voice, Tone,
/// Speed, I speak (Auto-detect or a language the ear supports), Read replies
/// aloud, Correct what I say and Try it. Each change PUTs the whole object.
class VoiceSection extends ConsumerWidget {
  const VoiceSection({super.key, required this.bot});

  final BotDetail bot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final info = ref.watch(voiceInfoProvider).valueOrNull;
    final on = info?.available ?? false;
    final v = bot.voice;
    String speaker() {
      final s = info?.speakers.where((s) => s.id == v.speaker).firstOrNull;
      return s == null ? v.speaker : '${s.name} · best in ${s.bestIn}';
    }

    return GroupedCard(
      label: 'Voice',
      children: [
        if (!on)
          const CardBody(child: Quiet(voiceOffText, key: Key('voice-off'))),
        InfoRow(
          key: const Key('voice-speaker'),
          label: 'Voice',
          value: info == null ? v.speaker : speaker(),
          onTap: on ? () => _pickSpeaker(context, ref, info!) : null,
        ),
        InfoRow(
          key: const Key('voice-tone'),
          label: 'Tone',
          value: info?.toneName(v.tone) ?? v.tone,
          onTap: on ? () => _pickTone(context, ref, info!) : null,
        ),
        InfoRow(
          key: const Key('voice-speed'),
          label: 'Speed',
          value: speedLabel(v.speed),
          onTap: on ? () => _pickSpeed(context, ref, info!) : null,
        ),
        SwitchRow(
          switchKey: const Key('voice-read-aloud'),
          label: 'Read replies aloud',
          caption: 'A reply plays by itself while its chat is open.',
          value: v.readAloud,
          onChanged: on
              ? (value) => _save(context, ref, v.copyWith(readAloud: value))
              : null,
        ),
        if (info != null && info.languages.isNotEmpty)
          InfoRow(
            key: const Key('voice-language'),
            label: 'I speak',
            value: info.languageName(v.language),
            onTap: on ? () => _pickLanguage(context, ref, info) : null,
          ),
        SwitchRow(
          switchKey: const Key('voice-correct-english'),
          label: 'Correct what I say',
          caption: correctSpeechHint,
          value: v.correctSpeech,
          onChanged: on
              ? (value) =>
                    _save(context, ref, v.copyWith(correctSpeech: value))
              : null,
        ),
        _TryIt(bot: bot, enabled: on),
      ],
    );
  }

  Future<void> _pickSpeaker(
    BuildContext context,
    WidgetRef ref,
    VoiceInfo info,
  ) async {
    final id = await _pick(context, [
      for (final s in info.speakers)
        (s.id, s.name, s.bestIn.isEmpty ? null : 'Best in ${s.bestIn}'),
    ], bot.voice.speaker);
    if (id != null && context.mounted) {
      await _save(context, ref, bot.voice.copyWith(speaker: id));
    }
  }

  Future<void> _pickTone(
    BuildContext context,
    WidgetRef ref,
    VoiceInfo info,
  ) async {
    final id = await _pick(context, [
      for (final t in info.tones) (t.id, t.name, null),
    ], bot.voice.tone);
    if (id != null && context.mounted) {
      await _save(context, ref, bot.voice.copyWith(tone: id));
    }
  }

  Future<void> _pickLanguage(
    BuildContext context,
    WidgetRef ref,
    VoiceInfo info,
  ) async {
    final id = await _pick(context, [
      for (final l in info.languages) (l.id, l.name, null),
    ], bot.voice.language);
    if (id != null && context.mounted) {
      await _save(context, ref, bot.voice.copyWith(language: id));
    }
  }

  Future<void> _pickSpeed(
    BuildContext context,
    WidgetRef ref,
    VoiceInfo info,
  ) async {
    final id = await _pick(context, [
      for (final s in info.speeds) ('$s', speedLabel(s), null),
    ], '${bot.voice.speed}');
    final speed = id == null ? null : double.tryParse(id);
    if (speed != null && context.mounted) {
      await _save(context, ref, bot.voice.copyWith(speed: speed));
    }
  }

  Future<void> _save(BuildContext context, WidgetRef ref, BotVoice next) async {
    if (next == bot.voice) return;
    await attempt(context, () async {
      final saved = await ref.read(voiceApiProvider).save(bot.id, next);
      ref.read(botDetailProvider(bot.id).notifier).replace(saved);
    });
  }
}

/// A sheet of choices (id, label, caption); the current one is ticked.
Future<String?> _pick(
  BuildContext context,
  List<(String, String, String?)> choices,
  String current,
) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    builder: (sheet) => SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(sheet).size.height * 0.7,
        ),
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final (id, label, caption) in choices)
              ListTile(
                key: Key('voice-choice-$id'),
                title: Text(label),
                subtitle: caption == null ? null : Text(caption),
                trailing: id == current
                    ? Icon(Icons.check, color: AccentColors.of(sheet).strong)
                    : null,
                onTap: () => Navigator.pop(sheet, id),
              ),
          ],
        ),
      ),
    ),
  );
}

/// Try it: the sample line in the chosen voice and tone, at its speed.
class _TryIt extends ConsumerWidget {
  const _TryIt({required this.bot, required this.enabled});

  final BotDetail bot;
  final bool enabled;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final key = 'sample:${bot.id}';
    final speech = ref.watch(speechProvider);
    final playing = speech.key == key;
    final canPlay = enabled && ref.watch(voicePlayerProvider).supported;
    ref.listen<SpeechState>(speechProvider, (_, next) {
      if (next.error != null && ModalRoute.of(context)?.isCurrent == true) {
        ScaffoldMessenger.maybeOf(
          context,
        )?.showSnackBar(SnackBar(content: Text(next.error!)));
      }
    });
    return CardBody(
      child: Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          key: const Key('voice-try'),
          onPressed: canPlay
              ? () => ref
                    .read(speechProvider.notifier)
                    .playSample(
                      key,
                      () => ref
                          .read(voiceApiProvider)
                          .sample(bot.id, bot.voice.speaker, bot.voice.tone),
                      bot.voice.speed,
                    )
              : null,
          icon: Icon(playing ? Icons.stop_rounded : Icons.play_arrow_rounded),
          label: Text(playing ? 'Stop' : 'Try it'),
        ),
      ),
    );
  }
}
