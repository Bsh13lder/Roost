import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/models.dart';
import '../api/providers.dart';
import '../api/reachability.dart';
import 'bot_frames.dart';

typedef SocketOpener = WebSocketChannel Function(
  Uri uri,
  Map<String, String> headers,
);

/// Overridden in tests; the default opens a real socket.
final socketOpenerProvider = Provider<SocketOpener>(
  (ref) => (uri, headers) => IOWebSocketChannel.connect(uri, headers: headers),
);

/// Every frame from `WS /api/events`, for the chat to read.
final frameBusProvider = Provider<StreamController<Frame>>((ref) {
  final bus = StreamController<Frame>.broadcast();
  ref.onDispose(bus.close);
  return bus;
});

class LiveState {
  const LiveState({this.bots = const {}, this.connected = false});

  final Map<String, Bot> bots;
  final bool connected;
}

/// Keeps one events socket open while signed in, reconnecting with a pause,
/// and resuming from the last cursor it saw.
class LiveController extends Notifier<LiveState> {
  WebSocketChannel? _channel;
  Timer? _retry;
  int _cursor = 0;
  int _failures = 0;
  bool _closed = false;

  @override
  LiveState build() {
    final auth = ref.watch(authProvider);
    // Riverpod keeps this notifier across rebuilds, and every rebuild runs
    // _close first: open again, or the socket would never reconnect.
    _closed = false;
    _failures = 0;
    ref.onDispose(_close);
    ref.listen<bool>(offlineProvider, (was, now) {
      if (was == true && !now) _reconnectNow();
    });
    if (auth.signedIn) Future.microtask(_connect);
    return const LiveState();
  }

  /// Roost answers again: try the socket now instead of after the backoff.
  void _reconnectNow() {
    final waiting = _retry?.isActive ?? false;
    if (_closed || !waiting) return;
    _retry!.cancel();
    _failures = 0;
    _connect();
  }

  /// Seed from REST so Home shows before the socket's snapshot arrives.
  void seed(List<Bot> bots) {
    if (state.bots.isNotEmpty) return;
    state = LiveState(
      bots: {for (final b in bots) b.id: b},
      connected: state.connected,
    );
  }

  void _connect() {
    if (_closed) return;
    final auth = ref.read(authProvider);
    final base = Uri.parse(auth.baseUrl);
    final uri = base.replace(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      path: '/api/events',
    );
    final WebSocketChannel channel;
    try {
      channel = ref.read(socketOpenerProvider)(uri, {
        'Origin': auth.baseUrl,
        'Cookie': 'roost_session=${auth.token}',
      });
    } catch (_) {
      _scheduleReconnect();
      return;
    }
    _channel = channel;
    channel.stream.listen(
      _onData,
      onDone: _scheduleReconnect,
      onError: (_) => _scheduleReconnect(),
    );
    if (_cursor > 0) {
      channel.sink.add(jsonEncode({'type': 'resume', 'cursor': _cursor}));
    }
  }

  void _onData(Object? data) {
    if (data is! String) return;
    final decoded = jsonDecode(data);
    if (decoded is! Map) return;
    final frame = decoded.cast<String, dynamic>();
    final seq = frame['cursor'] ?? frame['seq'];
    if (seq is int && seq > _cursor && frame['type'] != 'text_delta') {
      _cursor = seq;
    }
    _failures = 0;
    state = LiveState(
      bots: applyBotFrame(state.bots, frame),
      connected: true,
    );
    ref.read(frameBusProvider).add(frame);
  }

  void _scheduleReconnect() {
    if (_closed) return;
    state = LiveState(bots: state.bots);
    _retry?.cancel();
    _retry = Timer(reconnectDelay(_failures++), _connect);
    // A socket that keeps failing may mean the Mac is asleep: ask once over
    // HTTP, which shows the offline screen when nothing answers.
    if (_failures >= probeAfterSocketMisses) {
      unawaited(ref.read(offlineProvider.notifier).probe());
    }
  }

  void _close() {
    _closed = true;
    _retry?.cancel();
    _channel?.sink.close();
  }
}

final liveProvider =
    NotifierProvider<LiveController, LiveState>(LiveController.new);

/// Socket misses in a row before the app asks whether Roost is reachable.
const probeAfterSocketMisses = 2;

/// 1 s, 2 s, 4 s … up to 30 s between tries to reach the events socket.
Duration reconnectDelay(int failures) {
  final seconds = 1 << (failures > 5 ? 5 : failures);
  return Duration(seconds: seconds > 30 ? 30 : seconds);
}
