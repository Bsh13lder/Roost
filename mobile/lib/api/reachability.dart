import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api_error.dart';
import 'providers.dart';

/// How often the offline screen asks again while it is showing.
const offlineRetryInterval = Duration(seconds: 15);

/// One miss is not "offline": the phone's VPN (Tailscale) may still be waking
/// up. Roost is asked again after this pause, and only a miss then shows the
/// offline screen.
const offlineGrace = Duration(milliseconds: 1500);

/// A cheap signed-in read used to ask "is Roost there?".
const reachabilityProbePath = '/api/auth/me';

/// True while the gateway cannot be reached at all (refused, timed out, no
/// such host). Any reply, even a 401 or a 500, means it is reachable. The
/// one HTTP client reports both through its hooks, so no screen has to.
class ReachabilityController extends Notifier<bool> {
  Timer? _grace;
  bool _graceOver = false;

  @override
  bool build() {
    ref.listen(authProvider, (_, next) {
      if (!next.signedIn) _reset();
    });
    ref.onDispose(() => _grace?.cancel());
    return false;
  }

  /// A miss during the grace pause waits for the second look; a miss after
  /// it (or a miss while already offline) means offline.
  void markUnreachable() {
    if (state) return;
    if (_graceOver) {
      state = true;
      return;
    }
    _grace ??= Timer(offlineGrace, () {
      _graceOver = true;
      unawaited(probe());
    });
  }

  void markAnswered() => _reset();

  void _reset() {
    _grace?.cancel();
    _grace = null;
    _graceOver = false;
    if (state) state = false;
  }

  /// Asks the gateway once; the client's hooks update the state.
  Future<void> probe() async {
    try {
      await ref.read(apiClientProvider).get(reachabilityProbePath);
    } on ApiException {
      // The hooks have already recorded whether this was an answer.
    }
  }
}

final offlineProvider =
    NotifierProvider<ReachabilityController, bool>(ReachabilityController.new);
