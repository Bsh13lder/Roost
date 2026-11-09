import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/voice/just_audio_player.dart';

/// just_audio's shape: play() returns as soon as playback starts (or at
/// once when nothing follows), and a source finishes on its own later.
class _FakePort implements PlayerPort {
  final log = <String>[];
  final _state = StreamController<PlayerPhase>.broadcast();
  PlayerPhase _last = PlayerPhase.idle;
  int sources = 0;

  /// Like just_audio's processingStateStream: the last phase first.
  @override
  Stream<PlayerPhase> get phases => Stream.multi((c) {
        c.add(_last);
        final sub = _state.stream.listen(c.add);
        c.onCancel = sub.cancel;
      });

  void _emit(PlayerPhase p) {
    _last = p;
    _state.add(p);
  }

  @override
  Future<void> setBytes(Uint8List wav) async {
    sources++;
    log.add('source${String.fromCharCodes(wav)}');
    _emit(PlayerPhase.other); // loading
  }

  @override
  Future<void> setSpeed(double speed) async => log.add('speed$speed');

  @override
  Future<void> play() async => log.add('play');

  @override
  Future<void> stop() async {
    log.add('stop');
    _emit(PlayerPhase.idle);
  }

  void finish() => _emit(PlayerPhase.completed);
}

void main() {
  test('play waits for the sound to end, then stops, so parts never cut each other', () async {
    final port = _FakePort();
    final player = JustAudioVoicePlayer.withPort(port);
    final order = <String>[];
    Future<void> part(String name) async {
      await player.play(Uint8List.fromList(name.codeUnits), 1.0);
      order.add(name);
    }

    final all = () async {
      await part('A');
      await part('B');
      await part('C');
    }();
    await pumpEventQueue();
    expect(port.log, ['sourceA', 'speed1.0', 'play']);
    expect(order, isEmpty, reason: 'A still plays');
    port.finish();
    await pumpEventQueue();
    expect(order, ['A']);
    expect(port.log.sublist(3), ['stop', 'sourceB', 'speed1.0', 'play']);
    port.finish();
    await pumpEventQueue();
    port.finish();
    await all;
    expect(order, ['A', 'B', 'C']);
    expect(port.sources, 3);
  });

  test('stop while a part plays ends it at once', () async {
    final port = _FakePort();
    final player = JustAudioVoicePlayer.withPort(port);
    // The player starts idle, and the stream replays it: not an end.
    final playing = player.play(Uint8List.fromList('A'.codeUnits), 1.2);
    await pumpEventQueue();
    expect(port.log, ['sourceA', 'speed1.2', 'play']);
    await player.stop();
    await playing;
    expect(port.log, ['sourceA', 'speed1.2', 'play', 'stop', 'stop']);
  });
}
