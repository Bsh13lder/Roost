import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/session_store.dart';
import '../live/live_connection.dart' show SocketOpener, reconnectDelay;
import 'alert_rules.dart';
import 'notify_prefs.dart';

/// The Stay connected notification's line.
const connectedLine = 'Connected to your Mac';
const reconnectingLine = 'Reconnecting to your Mac…';
const signedOutLine = 'Sign in to Roost to get alerts';

/// How long a signed-out service waits before reading the session again.
const signedOutRetry = Duration(minutes: 1);

/// Shows alerts and the service's own status line.
abstract interface class AlertPresenter {
  Future<void> show(Alert alert);
  Future<void> status(String line);
}

/// The Stay connected service's work: one `/api/events` socket to the Mac,
/// kept open with a growing pause between tries and resumed from the last
/// cursor, each frame read by an [AlertBook]. It never reads a chat over HTTP.
class AlertPump {
  AlertPump({
    required SessionStore session,
    required SocketOpener open,
    required AlertPresenter presenter,
    required NotifyPrefs Function() prefs,
    DateTime Function()? now,
  })  : _session = session,
        _open = open,
        _presenter = presenter,
        _prefs = prefs,
        _now = now ?? DateTime.now;

  final SessionStore _session;
  final SocketOpener _open;
  final AlertPresenter _presenter;
  final NotifyPrefs Function() _prefs;
  final DateTime Function() _now;
  final AlertBook _book = AlertBook();

  /// What the app shows now (sent by the app; away when it is closed).
  AppFocus focus = AppFocus.away;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  Timer? _retry;
  int _cursor = 0;
  int _failures = 0;
  bool _stopped = false;
  bool _live = false;

  void start() {
    _stopped = false;
    unawaited(_connect());
  }

  void stop() {
    _stopped = true;
    _retry?.cancel();
    _sub?.cancel();
    _channel?.sink.close();
    _channel = null;
  }

  Future<void> _connect() async {
    if (_stopped) return;
    final base = await _session.readBaseUrl();
    final token = await _session.readToken();
    if (_stopped) return;
    if (base == null || token == null) {
      await _presenter.status(signedOutLine);
      _retry = Timer(signedOutRetry, () => unawaited(_connect()));
      return;
    }
    final url = Uri.parse(base);
    final uri = url.replace(scheme: url.scheme == 'https' ? 'wss' : 'ws', path: '/api/events');
    try {
      _channel = _open(uri, {'Origin': base, 'Cookie': 'roost_session=$token'});
    } catch (_) {
      _again();
      return;
    }
    _live = false;
    _sub = _channel!.stream.listen(_onData, onDone: _again, onError: (_) => _again(), cancelOnError: true);
    if (_cursor > 0) _channel!.sink.add(jsonEncode({'type': 'resume', 'cursor': _cursor}));
  }

  void _onData(dynamic data) {
    if (data is! String) return;
    final Object? decoded;
    try {
      decoded = jsonDecode(data);
    } on FormatException {
      return;
    }
    if (decoded is! Map) return;
    final frame = decoded.cast<String, dynamic>();
    final seq = frame['cursor'] ?? frame['seq'];
    if (seq is int && seq > _cursor && frame['type'] != 'text_delta') _cursor = seq;
    _failures = 0;
    if (!_live) {
      _live = true;
      unawaited(_presenter.status(connectedLine));
    }
    final alert = _book.take(frame, prefs: _prefs(), focus: focus, now: _now());
    if (alert != null) unawaited(_presenter.show(alert));
  }

  void _again() {
    if (_stopped) return;
    _sub?.cancel();
    _channel = null;
    unawaited(_presenter.status(reconnectingLine));
    _retry?.cancel();
    _retry = Timer(reconnectDelay(_failures++), () => unawaited(_connect()));
  }
}
