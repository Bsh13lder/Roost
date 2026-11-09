import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/call/endpointer.dart';

/// [ms] of PCM16 at 16 kHz: a sine at [amp] (0 = silence).
Uint8List tone(int ms, {double amp = 0.3}) {
  final n = ms * 16;
  final out = ByteData(n * 2);
  for (var i = 0; i < n; i++) {
    final v = (sin(i * 2 * pi * 220 / 16000) * amp * 32767).round();
    out.setInt16(i * 2, v, Endian.little);
  }
  return out.buffer.asUint8List();
}

Uint8List quiet(int ms) => tone(ms, amp: 0.0005);

/// A sine whose RMS level is [dbfs].
Uint8List toneAt(int ms, double dbfs) => tone(ms, amp: pow(10, dbfs / 20) * sqrt2);

/// Feeds [audio] in 100 ms chunks; the utterances that came out.
List<Uint8List> feedAll(Endpointer e, List<Uint8List> audio) {
  final bytes = BytesBuilder()..add(audio.expand((a) => a).toList());
  final all = bytes.takeBytes();
  final out = <Uint8List>[];
  for (var at = 0; at < all.length; at += 3200) {
    final r = e.feed(Uint8List.sublistView(all, at, min(at + 3200, all.length)));
    if (r != null) out.add(r);
  }
  return out;
}

void main() {
  test('the shared constants (contract E)', () {
    expect(endpointerFrameMs, 20);
    expect(endpointerEndSilenceMs, 700);
    expect(endpointerStartMs, 120);
    expect(endpointerMinSpeechMs, 350);
    expect(endpointerMaxMs, 30000);
    expect(endpointerPreRollMs, 300);
    expect(endpointerMinDb, -50.0);
    expect(endpointerOverFloorDb, 10.0);
    expect(endpointerEndOverFloorDb, lessThan(endpointerOverFloorDb));
    expect(endpointerGuardStartMs, 300);
  });

  test('speech then a pause is one utterance, with a little before it', () {
    final e = Endpointer();
    final got = feedAll(e, [quiet(1000), tone(1200), quiet(1200)]);
    expect(got, hasLength(1));
    final ms = got.single.length ~/ 32;
    expect(ms, greaterThanOrEqualTo(1200 + endpointerPreRollMs ~/ 2));
    expect(ms, lessThan(1200 + endpointerPreRollMs + endpointerEndSilenceMs + 200));
  });

  test('silence and a short click are never sent', () {
    final e = Endpointer();
    expect(feedAll(e, [quiet(3000)]), isEmpty);
    expect(feedAll(e, [tone(120), quiet(1500)]), isEmpty);
  });

  test('a 20 ms click never even starts a turn', () {
    final e = Endpointer();
    feedAll(e, [quiet(500), tone(20), quiet(100)]);
    expect(e.speaking, isFalse);
    feedAll(e, [tone(60), quiet(100)]);
    expect(e.speaking, isFalse);
    feedAll(e, [tone(140)]);
    expect(e.speaking, isTrue);
  });

  test('a soft voice at -46 dBFS starts a turn', () {
    final e = Endpointer();
    final got = feedAll(e, [quiet(1000), toneAt(1000, -46), quiet(1200)]);
    expect(got, hasLength(1));
  });

  test('a short pause inside a sentence does not cut it', () {
    final e = Endpointer();
    final got = feedAll(e, [tone(800), quiet(400), tone(800), quiet(1200)]);
    expect(got, hasLength(1));
  });

  test('a long speech is cut at the limit', () {
    final e = Endpointer(maxMs: 2000);
    final got = feedAll(e, [tone(5000)]);
    expect(got, isNotEmpty);
    expect(got.first.length ~/ 32, lessThanOrEqualTo(2000 + endpointerPreRollMs + 100));
  });

  test('the level rises with the voice and speaking is reported', () {
    final e = Endpointer();
    feedAll(e, [quiet(500)]);
    expect(e.level, lessThan(0.2));
    expect(e.speaking, isFalse);
    feedAll(e, [tone(300)]);
    expect(e.level, greaterThan(0.6));
    expect(e.speaking, isTrue);
    e.reset();
    expect(e.speaking, isFalse);
  });

  test('odd chunk sizes are fine', () {
    final e = Endpointer();
    final audio = [...tone(1000), ...quiet(1200)];
    final out = <Uint8List>[];
    for (var at = 0; at < audio.length; at += 777) {
      final r = e.feed(Uint8List.fromList(audio.sublist(at, min(at + 777, audio.length))));
      if (r != null) out.add(r);
    }
    expect(out, hasLength(1));
    expect(out.single.length.isEven, isTrue);
  });

  test('guarded, the speaker\'s residual at -35 dBFS is ignored; a real voice is not', () {
    final e = Endpointer()..guard(true);
    expect(e.guarded, isTrue);
    feedAll(e, [quiet(300), toneAt(1500, -35)]);
    expect(e.speaking, isFalse);
    feedAll(e, [tone(400)]);
    expect(e.speaking, isTrue);
  });

  test('guarded, the room floor is frozen', () {
    final e = Endpointer();
    feedAll(e, [quiet(1000)]);
    final before = e.floorDb;
    // Room noise above the old floor but under the start bar.
    e.guard(true);
    feedAll(e, [toneAt(2000, -56)]);
    expect(e.floorDb, before);
    e.guard(false);
    feedAll(e, [toneAt(2000, -56)]);
    expect(e.floorDb, greaterThan(before));
  });

  test('flush hands the turn back now', () {
    final e = Endpointer();
    expect(e.flush(), isNull);
    feedAll(e, [quiet(300), tone(500)]);
    expect(e.speaking, isTrue);
    final got = e.flush();
    expect(got, isNotNull);
    expect(got!.length ~/ 32, greaterThanOrEqualTo(500));
    expect(e.speaking, isFalse);
    feedAll(e, [tone(100)]);
    expect(e.flush(), isNull, reason: 'too short to be a word');
  });

  test('a turn ends on a quieter threshold than it starts (hysteresis)', () {
    final e = Endpointer();
    // Starts well above the floor, then drops to a level between the two
    // thresholds: still part of the turn, so no end until real quiet.
    feedAll(e, [quiet(1000), tone(600), toneAt(1000, -47)]);
    expect(e.speaking, isTrue);
    final got = feedAll(e, [quiet(1200)]);
    expect(got, hasLength(1));
    expect(got.single.length ~/ 32, greaterThanOrEqualTo(1600));
  });
}
