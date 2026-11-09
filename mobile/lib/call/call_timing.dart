import 'package:flutter/foundation.dart';

/// How long the call waits for each thing (shared contract E and G; the
/// phone's copy). Tests pass shorter ones.
@immutable
class CallTiming {
  const CallTiming({
    this.heartbeat = const Duration(seconds: 20),
    this.micStall = const Duration(seconds: 3),
    this.speakerTail = const Duration(milliseconds: 300),
    this.hearing = const Duration(seconds: 20),
    this.thinking = const Duration(seconds: 120),
    this.stillOnItAfter = const Duration(seconds: 15),
    this.stillOnItEvery = const Duration(seconds: 30),
    this.livePoll = const Duration(milliseconds: 400),
    this.liveStall = const Duration(seconds: 5),
  });

  /// `POST /api/threads/{id}/call` this often (VOICE_CALL_HEARTBEAT_S).
  final Duration heartbeat;

  /// No chunk from the mic for this long while listening: open it again.
  final Duration micStall;

  /// After the bot's voice ends, before the mic arms again (SPEAKER_TAIL_MS).
  final Duration speakerTail;

  /// The longest a transcription may take (CALL_HEARING_TIMEOUT_S).
  final Duration hearing;

  /// The longest the bot may think before the call listens again
  /// (CALL_THINKING_TIMEOUT_S).
  final Duration thinking;

  /// Thinking with no words yet for this long: the still_on_it line
  /// (CALL_STILL_ON_IT_AFTER_S), then every [stillOnItEvery], at most
  /// [stillOnItMax] times.
  final Duration stillOnItAfter;
  final Duration stillOnItEvery;

  /// Polling `GET …/live-speech/{id}` when no frame comes.
  final Duration livePoll;

  /// Live speech whose done never came, once the run is over: let it go.
  final Duration liveStall;

  static const stillOnItMax = 3;

  CallTiming copyWith({
    Duration? heartbeat,
    Duration? micStall,
    Duration? speakerTail,
    Duration? hearing,
    Duration? thinking,
    Duration? stillOnItAfter,
    Duration? stillOnItEvery,
    Duration? livePoll,
    Duration? liveStall,
  }) =>
      CallTiming(
        heartbeat: heartbeat ?? this.heartbeat,
        micStall: micStall ?? this.micStall,
        speakerTail: speakerTail ?? this.speakerTail,
        hearing: hearing ?? this.hearing,
        thinking: thinking ?? this.thinking,
        stillOnItAfter: stillOnItAfter ?? this.stillOnItAfter,
        stillOnItEvery: stillOnItEvery ?? this.stillOnItEvery,
        livePoll: livePoll ?? this.livePoll,
        liveStall: liveStall ?? this.liveStall,
      );
}
