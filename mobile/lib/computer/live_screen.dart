import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/providers.dart';
import '../live/live_connection.dart';
import 'rfb_session.dart';

/// Opens `WS /api/bots/{id}/live` as the signed-in user: view only, or
/// control while you hold the computer.
WebSocketChannel openLiveSocket(
  SocketOpener open,
  AuthState auth,
  String botId, {
  required bool control,
}) {
  final base = Uri.parse(auth.baseUrl);
  final uri = base.replace(
    scheme: base.scheme == 'https' ? 'wss' : 'ws',
    path: '/api/bots/$botId/live',
    queryParameters: {'mode': control ? 'control' : 'view'},
  );
  return open(uri, {
    'Origin': auth.baseUrl,
    'Cookie': 'roost_session=${auth.token}',
  });
}

enum LiveScreenPhase { connecting, live, asleep, unreachable }

/// Pauses before trying a watched screen again: a computer that is waking up
/// for the bot answers within a few seconds.
const liveScreenRetries = [
  Duration(seconds: 2),
  Duration(seconds: 4),
  Duration(seconds: 8),
];

/// A bot's screen, view only, shared by everything that shows it (the chat's
/// card and its sheet): one socket while anything watches, closed when
/// nothing does. It never wakes the computer.
class LiveScreen extends ChangeNotifier {
  LiveScreen(this._open, {this.retries = liveScreenRetries});

  final WebSocketChannel Function() _open;
  final List<Duration> retries;
  RfbSession? _session;
  Timer? _retry;
  int _tries = 0;
  bool _disposed = false;

  LiveScreenPhase phase = LiveScreenPhase.connecting;

  /// The live session while [phase] is live.
  RfbSession? get session => _session;

  void start() => _connect();

  /// Try again now with a fresh set of retries (after the computer was woken).
  void reconnect() {
    _retry?.cancel();
    _tries = 0;
    _connect();
  }

  void _connect() {
    if (_disposed) return;
    _session?.dispose();
    try {
      _session = RfbSession(_open(), controlling: false)
        ..addListener(_onSession);
    } catch (_) {
      _session = null;
      _closed(null);
      return;
    }
    _set(LiveScreenPhase.connecting);
  }

  void _onSession() {
    final s = _session;
    if (s == null || _disposed) return;
    if (s.state == SessionState.live) {
      _tries = 0;
      if (phase != LiveScreenPhase.live) _set(LiveScreenPhase.live);
    } else if (s.state == SessionState.closed) {
      _closed(s.closeCode);
    }
  }

  void _closed(int? code) {
    final again = _tries < retries.length;
    if (again) {
      _retry?.cancel();
      _retry = Timer(retries[_tries++], _connect);
    }
    _set(
      code == closeAsleep
          ? LiveScreenPhase.asleep
          : again
          ? LiveScreenPhase.connecting
          : LiveScreenPhase.unreachable,
    );
  }

  void _set(LiveScreenPhase next) {
    if (_disposed) return;
    phase = next;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _retry?.cancel();
    _session?.dispose();
    _session = null;
    super.dispose();
  }
}

/// One shared view-only screen per bot, closed when the last watcher leaves.
final liveScreenProvider = ChangeNotifierProvider.autoDispose
    .family<LiveScreen, String>((ref, botId) {
      final auth = ref.read(authProvider);
      final open = ref.read(socketOpenerProvider);
      return LiveScreen(() => openLiveSocket(open, auth, botId, control: false))
        ..start();
    });
