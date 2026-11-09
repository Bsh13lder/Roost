import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/call/call_controller.dart';

import 'call_controller_test.dart' show Rig, msg, wait;

Message fixLine(String id, String forMessage, {String said = 'Add milk', int seq = 5}) =>
    Message(
      id: id,
      threadId: 't1',
      role: 'activity',
      body: jsonEncode({
        'message_id': forMessage,
        'said': said,
        'corrected': 'Add some milk',
        'fixes': [
          {'wrong': 'milk', 'right': 'some milk'},
        ],
      }),
      seq: seq,
      createdAt: '',
      kind: 'english_fix',
    );

void main() {
  group('the corrected copy of what you said', () {
    test('an english_fix for this turn\'s message replaces the plain caption', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      expect(r.call.heardFix, isNull);
      // Your own message, as the chat adds it after the send.
      final mine = msg('u1', 'user', body: 'Add milk');
      r.chat([msg('old', 'bot'), mine], BotStatus.onIt);
      r.chat([msg('old', 'bot'), mine, fixLine('f1', 'u1')], BotStatus.onIt);
      expect(r.call.heardFix?.corrected, 'Add some milk');
      expect(r.call.heard, 'Add milk');
      expect(r.call.phase, CallPhase.thinking, reason: 'the line changes nothing else');
    });

    test('an english_fix for another message, or one from before the call, is not yours', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      final mine = msg('u1', 'user', body: 'Add milk');
      r.chat([msg('old', 'bot'), fixLine('f0', 'u0', said: 'Hi'), mine, fixLine('f1', 'u9')], BotStatus.onIt);
      expect(r.call.heardFix, isNull);
    });

    test('a fix that is still being tied to your message is matched by its words when the id is unknown', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      // The chat has not shown your message yet, only the fix.
      r.chat([msg('old', 'bot'), fixLine('f1', 'u-unknown', said: 'Add milk')], BotStatus.onIt);
      expect(r.call.heardFix?.corrected, 'Add some milk');
    });

    test('the next turn forgets the last fix', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      final mine = msg('u1', 'user', body: 'Add milk');
      r.chat([msg('old', 'bot'), mine, fixLine('f1', 'u1')], BotStatus.onIt);
      expect(r.call.heardFix, isNotNull);
      r.chat([msg('old', 'bot'), mine, fixLine('f1', 'u1'), msg('r1', 'bot')], BotStatus.resting);
      await pumpEventQueue();
      expect(r.call.heardFix, isNotNull, reason: 'it stays while the reply is spoken');
      r.speaking.complete();
      await wait(5);
      expect(r.call.phase, CallPhase.listening);
      await r.turn();
      expect(r.call.heardFix, isNull);
    });
  });
}
