// ignore_for_file: depend_on_referenced_packages
import 'dart:async';
import 'dart:convert';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/notify/alert_pump.dart';
import 'package:roost_mobile/notify/alert_rules.dart';
import 'package:roost_mobile/notify/notify_prefs.dart';

import '../fake_socket.dart';

class RecordingPresenter implements AlertPresenter {
  final shown = <Alert>[];
  final lines = <String>[];
  @override
  Future<void> show(Alert alert) async => shown.add(alert);
  @override
  Future<void> status(String line) async => lines.add(line);
}

String frame(Map<String, Object?> f) => jsonEncode(f);

final snapshot = frame({
  'type': 'snapshot',
  'cursor': 4,
  'bots': [
    {'id': 'b1', 'name': 'Chief', 'notify': true},
  ],
});

String card(String id, {int cursor = 5}) => frame({
      'type': 'message',
      'cursor': cursor,
      'thread_id': 't1',
      'message': {
        'id': 'm$id',
        'role': 'bot',
        'kind': 'approval',
        'body': jsonEncode({'card_id': id, 'kind': 'ask', 'steps': ["Click 'Send'"]}),
        'author_bot_id': 'b1',
        'tainted': false,
      },
    });

void main() {
  late List<FakeSocket> sockets;
  late List<(Uri, Map<String, String>)> opened;
  late RecordingPresenter presenter;

  AlertPump pump({MemorySessionStore? store}) {
    sockets = [];
    opened = [];
    presenter = RecordingPresenter();
    return AlertPump(
      session: store ??
          (MemorySessionStore()
            ..url = 'https://mac.example.ts.net'
            ..token = 'tok'),
      open: (uri, headers) {
        opened.add((uri, headers));
        final s = FakeSocket();
        sockets.add(s);
        return s;
      },
      presenter: presenter,
      prefs: () => const NotifyPrefs(stayConnected: true),
      now: () => DateTime.utc(2026, 10, 23, 10),
    );
  }

  test('opens the events socket with the session and shows a waiting card', () {
    fakeAsync((async) {
      final p = pump()..start();
      async.flushMicrotasks();
      final (uri, headers) = opened.single;
      expect(uri.toString(), 'wss://mac.example.ts.net/api/events');
      expect(headers['Origin'], 'https://mac.example.ts.net');
      expect(headers['Cookie'], 'roost_session=tok');
      sockets.single.incoming
        ..add(snapshot)
        ..add(card('c1'));
      async.flushMicrotasks();
      expect(presenter.shown.single.title, 'Chief needs your OK');
      expect(presenter.lines.last, connectedLine);
      p.stop();
    });
  });

  test('reconnects with a pause, resumes from the last cursor, and never repeats a card', () {
    fakeAsync((async) {
      final p = pump()..start();
      async.flushMicrotasks();
      sockets.single.incoming
        ..add(snapshot)
        ..add(card('c1'));
      async.flushMicrotasks();
      unawaited(sockets.single.incoming.close());
      async.flushMicrotasks();
      expect(presenter.lines.last, reconnectingLine);
      expect(sockets.length, 1);
      async.elapse(const Duration(seconds: 1));
      expect(sockets.length, 2);
      expect(jsonDecode(sockets.last.sentText.single), {'type': 'resume', 'cursor': 5});
      sockets.last.incoming
        ..add(snapshot)
        ..add(card('c1'));
      async.flushMicrotasks();
      expect(presenter.shown.length, 1);
      p.stop();
    });
  });

  test('a phone that is still on the open chat gets nothing for it', () {
    fakeAsync((async) {
      final p = pump()..start();
      async.flushMicrotasks();
      p.focus = const AppFocus(visible: true, openChatBotId: 'b1');
      sockets.single.incoming
        ..add(snapshot)
        ..add(card('c1'));
      async.flushMicrotasks();
      expect(presenter.shown, isEmpty);
      p.stop();
    });
  });

  test('signed out: says so and asks again later, opening nothing', () {
    fakeAsync((async) {
      final p = pump(store: MemorySessionStore())..start();
      async.flushMicrotasks();
      expect(opened, isEmpty);
      expect(presenter.lines.last, signedOutLine);
      async.elapse(signedOutRetry);
      expect(opened, isEmpty);
      p.stop();
    });
  });

  test('stop closes the socket and nothing reconnects', () {
    fakeAsync((async) {
      final p = pump()..start();
      async.flushMicrotasks();
      p.stop();
      expect(sockets.single.closed, isTrue);
      async.elapse(const Duration(minutes: 5));
      expect(sockets.length, 1);
    });
  });

  test('a garbled frame is ignored', () {
    fakeAsync((async) {
      final p = pump()..start();
      async.flushMicrotasks();
      sockets.single.incoming
        ..add('not json')
        ..add(jsonEncode([1, 2]))
        ..add(snapshot)
        ..add(card('c2'));
      async.flushMicrotasks();
      expect(presenter.shown.single.key, 'card:c2');
      p.stop();
    });
  });
}
