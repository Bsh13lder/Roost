import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/call/call_controller.dart';
import 'package:roost_mobile/live/bot_frames.dart';

import 'call_controller_test.dart';

Frame ready(int part, {bool done = false, String id = 'r1'}) =>
    {'type': 'speech_ready', 'thread_id': 't1', 'message_id': id, 'part': part, 'done': done};

final placeholder = [msg('old', 'bot'), msg('u1', 'user'), msg('r1', 'bot', seq: 0, body: '')];

void main() {
  group('speaking as the reply streams', () {
    test('parts are spoken in frame order; the stored reply is never fetched too', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat(placeholder, BotStatus.onIt);
      await pumpEventQueue();
      expect(r.live, isEmpty, reason: 'nothing to say yet');
      r.frames.add(ready(0));
      await pumpEventQueue();
      expect(r.live, [('t1', 'r1')]);
      expect(r.liveEvents.last.ready, 1);
      expect(r.call.phase, CallPhase.speaking);
      r.frames.add(ready(1));
      r.frames.add(ready(2, done: true));
      await pumpEventQueue();
      expect(r.liveEvents.last, (ready: 3, done: true, speed: null));
      r.chat([...placeholder.sublist(0, 2), msg('r1', 'bot', seq: 3, body: 'Done!')], BotStatus.resting);
      expect(r.spoken, isEmpty);
      expect(r.call.phase, CallPhase.speaking);
      r.liveSpeaking.complete();
      await pumpEventQueue();
      await wait(10);
      expect(r.call.phase, CallPhase.listening);
    });

    test('frames for another message are ignored', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat(placeholder, BotStatus.onIt);
      r.frames.add(ready(0, id: 'other'));
      await pumpEventQueue();
      expect(r.live, isEmpty);
      expect(r.call.phase, CallPhase.thinking);
    });

    test('with no frames, polling finds the parts', () async {
      final r = Rig()..livePlan = (parts: 1, done: true, speed: 1.0);
      await r.up();
      await r.turn();
      r.chat(placeholder, BotStatus.onIt);
      await wait(60);
      expect(r.live, [('t1', 'r1')]);
      expect(r.liveEvents.last, (ready: 1, done: true, speed: 1.0));
      expect(r.call.phase, CallPhase.speaking);
    });

    test('an old server: the stored reply is spoken after the run, as before', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat(placeholder, BotStatus.onIt);
      await wait(40);
      final done = [...placeholder.sublist(0, 2), msg('r1', 'bot', seq: 3, body: 'Done!')];
      r.chat(done, BotStatus.resting);
      expect(r.live, isEmpty);
      expect(r.spoken, ['r1']);
      expect(r.call.phase, CallPhase.speaking);
    });

    test('live speech that never says done is let go once the run is over', () async {
      final r = Rig(timing: quietTiming.copyWith(liveStall: const Duration(milliseconds: 30)));
      await r.up();
      await r.turn();
      r.chat(placeholder, BotStatus.onIt);
      r.frames.add(ready(0));
      await pumpEventQueue();
      r.chat([...placeholder.sublist(0, 2), msg('r1', 'bot', seq: 3, body: 'Done!')], BotStatus.resting);
      await wait(60);
      expect(r.liveEvents.last.done, isTrue);
    });

    test('captions follow the streamed text without its lead', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat(placeholder, BotStatus.onIt, streaming: {'r1': 'On it: checking.'});
      expect(r.call.saying, 'Checking.');
      r.chat(placeholder, BotStatus.onIt, streaming: {'r1': 'On it: checking.\nMilk is there.'});
      expect(r.call.saying, 'Milk is there.');
    });

    test('still_on_it after a long quiet, at most three times, never once words stream', () async {
      final r = Rig(
        timing: quietTiming.copyWith(
          stillOnItAfter: const Duration(milliseconds: 20),
          stillOnItEvery: const Duration(milliseconds: 20),
        ),
      );
      await r.up();
      await r.turn();
      r.chat(placeholder, BotStatus.onIt);
      await wait(130);
      expect(r.lines.where((l) => l == 'still_on_it').length, 3);
      final r2 = Rig(timing: quietTiming.copyWith(stillOnItAfter: const Duration(milliseconds: 20)));
      await r2.up();
      await r2.turn();
      r2.chat(placeholder, BotStatus.onIt, streaming: {'r1': 'Hi'});
      await wait(50);
      expect(r2.lines, isNot(contains('still_on_it')));
    });
  });

  group('cutting in', () {
    test('talking over the bot stops it, tells the server, and your words survive', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat([msg('old', 'bot'), msg('r1', 'bot', body: 'Long answer.')], BotStatus.resting);
      expect(r.call.phase, CallPhase.speaking);
      await r.mic.say();
      await pumpEventQueue();
      expect(r.stops, 1);
      expect(r.haptics, 1);
      expect(r.beats.last, 'r1');
      expect(r.transcribed, hasLength(2));
      expect(r.sent, hasLength(2));
    });

    test('room noise under the guard does not cut in', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat([msg('old', 'bot'), msg('r1', 'bot')], BotStatus.resting);
      r.mic.pushQuiet(ms: 2000);
      await pumpEventQueue();
      expect(r.stops, 0);
      expect(r.call.phase, CallPhase.speaking);
    });

    test('tapping while it speaks stops it and listens', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat([msg('r1', 'bot')], BotStatus.resting);
      expect(r.call.phase, CallPhase.speaking);
      await r.call.orbTapped();
      expect(r.stops, 1);
      expect(r.call.phase, CallPhase.listening);
    });
  });

  group('goodbye', () {
    test('a goodbye word says bye and ends without sending', () async {
      final r = Rig(heard: 'Bye!');
      await r.up();
      await r.turn();
      expect(r.sent, isEmpty);
      expect(r.lines.last, 'bye');
      expect(r.call.phase, CallPhase.ended);
      expect(r.ends, 1);
      expect(r.mic.closed, isTrue);
    });

    test('"bye the way" is just words', () async {
      final r = Rig(heard: 'bye the way, add eggs');
      await r.up();
      await r.turn();
      expect(r.sent, ['bye the way, add eggs']);
    });
  });
}
