import 'package:flutter/foundation.dart';

/// Roost voice (docs/plans/2026-10-30-roost-voice.md §2): the fixed values
/// the phone shares with the gateway.
const defaultSpeaker = 'aiden';
const defaultTone = 'natural';
const defaultSpeed = 1.0;

/// Voice tuning D2 (docs/plans/2026-11-06-roost-voice-tuning.md): the ear
/// reads the language itself unless the bot's voice names one.
const voiceLanguageAuto = 'auto';

/// What the gateway says when the Mac's voice service doesn't answer.
const voiceOffText = "Voice isn't running on your Mac yet.";

/// The longest recording the gateway takes, and the rate the phone records at.
const voiceMaxSeconds = 120;
const voiceSampleRate = 16000;

/// Live words while recording (voice tuning D4): the buffer so far goes for
/// a partial transcript this often, while it is at most this long (the
/// server's VOICE_PARTIAL_EVERY_MS and VOICE_PARTIAL_MAX_S).
const voicePartialEvery = Duration(milliseconds: 1000);
const voicePartialMaxSeconds = 30;

/// A bot's voice: `voice` on every bot (`GET /api/bots`, `bot_updated`).
/// Anything missing or of the wrong type reads as the defaults.
@immutable
class BotVoice {
  const BotVoice({
    this.speaker = defaultSpeaker,
    this.tone = defaultTone,
    this.speed = defaultSpeed,
    this.readAloud = false,
    this.correctSpeech = false,
    this.language = voiceLanguageAuto,
  });

  factory BotVoice.fromJson(Object? json) {
    if (json is! Map) return const BotVoice();
    final speaker = json['speaker'];
    final tone = json['tone'];
    final speed = json['speed'];
    final language = json['language'];
    return BotVoice(
      speaker: speaker is String && speaker.isNotEmpty
          ? speaker
          : defaultSpeaker,
      tone: tone is String && tone.isNotEmpty ? tone : defaultTone,
      speed: speed is num && speed > 0 ? speed.toDouble() : defaultSpeed,
      readAloud: json['read_aloud'] == true,
      // The switch under its new name, else its old one (an older gateway);
      // an older row without either reads false.
      correctSpeech: json.containsKey('correct_speech')
          ? json['correct_speech'] == true
          : json['correct_english'] == true,
      language: language is String && language.isNotEmpty
          ? language
          : voiceLanguageAuto,
    );
  }

  final String speaker;
  final String tone;
  final double speed;
  final bool readAloud;

  /// Correct what I say (voice tuning D3): a corrected copy of what you say,
  /// in any language, mistakes marked.
  final bool correctSpeech;

  /// The switch under its old name (§4's Correct my English).
  bool get correctEnglish => correctSpeech;

  /// The language you speak to this bot: [voiceLanguageAuto] or a code from
  /// `GET /api/voice`'s languages.
  final String language;

  BotVoice copyWith({
    String? speaker,
    String? tone,
    double? speed,
    bool? readAloud,
    bool? correctSpeech,
    String? language,
  }) => BotVoice(
    speaker: speaker ?? this.speaker,
    tone: tone ?? this.tone,
    speed: speed ?? this.speed,
    readAloud: readAloud ?? this.readAloud,
    correctSpeech: correctSpeech ?? this.correctSpeech,
    language: language ?? this.language,
  );

  /// The whole object, as `PUT /api/bots/{id}/voice` takes it: the switch
  /// under both names, so an older gateway still reads it.
  Map<String, Object> toJson() => {
    'speaker': speaker,
    'tone': tone,
    'speed': speed,
    'read_aloud': readAloud,
    'correct_speech': correctSpeech,
    'correct_english': correctSpeech,
    'language': language,
  };

  @override
  bool operator ==(Object other) =>
      other is BotVoice &&
      other.speaker == speaker &&
      other.tone == tone &&
      other.speed == speed &&
      other.readAloud == readAloud &&
      other.correctSpeech == correctSpeech &&
      other.language == language;

  @override
  int get hashCode =>
      Object.hash(speaker, tone, speed, readAloud, correctSpeech, language);
}

@immutable
class VoiceSpeaker {
  const VoiceSpeaker(this.id, this.name, this.bestIn);
  final String id, name, bestIn;
}

@immutable
class VoiceTone {
  const VoiceTone(this.id, this.name);
  final String id, name;
}

/// One language the ear supports, or Auto-detect (voice tuning D2).
@immutable
class VoiceLanguage {
  const VoiceLanguage(this.id, this.name);
  final String id, name;
}

/// One fix in a correction: the words as heard and the words that are right.
@immutable
class SpeechFix {
  const SpeechFix(this.wrong, this.right);
  final String wrong, right;

  Map<String, String> toJson() => {'wrong': wrong, 'right': right};

  @override
  bool operator ==(Object other) =>
      other is SpeechFix && other.wrong == wrong && other.right == right;

  @override
  int get hashCode => Object.hash(wrong, right);
}

/// `POST /api/voice/correct` (voice tuning D3): the cleaned words and each
/// fix; [changed] false means the words were fine (or the check is off).
@immutable
class SpeechCorrection {
  const SpeechCorrection({
    required this.corrected,
    required this.fixes,
    required this.changed,
  });

  factory SpeechCorrection.fromJson(Object? json, String said) {
    if (json is! Map) {
      return SpeechCorrection(corrected: said, fixes: const [], changed: false);
    }
    final corrected = json['corrected'];
    final fixes = json['fixes'];
    return SpeechCorrection(
      corrected: corrected is String && corrected.isNotEmpty ? corrected : said,
      fixes: [
        for (final f in (fixes is List ? fixes : const []))
          if (f is Map && f['wrong'] is String && f['right'] is String)
            SpeechFix(f['wrong'] as String, f['right'] as String),
      ],
      changed: json['changed'] == true,
    );
  }

  final String corrected;
  final List<SpeechFix> fixes;
  final bool changed;
}

/// `GET /api/voice`.
@immutable
class VoiceInfo {
  const VoiceInfo({
    this.available = false,
    this.speakers = const [],
    this.tones = const [],
    this.speeds = const [],
    this.languages = const [],
  });

  factory VoiceInfo.fromJson(Object? json) {
    if (json is! Map) return const VoiceInfo();
    List<Map> maps(Object? v) => [
      for (final x in (v is List ? v : const []))
        if (x is Map) x,
    ];
    String s(Object? v) => v is String ? v : '';
    return VoiceInfo(
      available: json['available'] == true,
      speakers: [
        for (final m in maps(json['speakers']))
          if (s(m['id']).isNotEmpty)
            VoiceSpeaker(s(m['id']), s(m['name']), s(m['best_in'])),
      ],
      tones: [
        for (final m in maps(json['tones']))
          if (s(m['id']).isNotEmpty) VoiceTone(s(m['id']), s(m['name'])),
      ],
      speeds: [
        for (final x
            in (json['speeds'] is List ? json['speeds'] as List : const []))
          if (x is num) x.toDouble(),
      ],
      // Missing on an older gateway: no pick is shown.
      languages: [
        for (final m in maps(json['languages']))
          if (s(m['id']).isNotEmpty) VoiceLanguage(s(m['id']), s(m['name'])),
      ],
    );
  }

  final bool available;
  final List<VoiceSpeaker> speakers;
  final List<VoiceTone> tones;
  final List<double> speeds;
  final List<VoiceLanguage> languages;

  String speakerName(String id) {
    for (final s in speakers) {
      if (s.id == id) return s.name;
    }
    return id;
  }

  String toneName(String id) {
    for (final t in tones) {
      if (t.id == id) return t.name;
    }
    return id;
  }

  String languageName(String id) {
    for (final l in languages) {
      if (l.id == id) return l.name;
    }
    return id == voiceLanguageAuto ? 'Auto-detect' : id;
  }
}

/// "1×", "1.25×", "0.9×".
String speedLabel(double speed) {
  var text = speed.toStringAsFixed(2);
  while (text.contains('.') && (text.endsWith('0') || text.endsWith('.'))) {
    text = text.substring(0, text.length - 1);
  }
  return '$text×';
}

/// "0:07", "1:59".
String recordingClock(int seconds) =>
    '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
