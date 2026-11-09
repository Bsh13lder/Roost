import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/api_error.dart';
import '../api/providers.dart';
import '../live/live_connection.dart';
import '../nav/main_back.dart';
import '../theme/tokens.dart';
import 'computer_api.dart';
import 'done_forms.dart';
import 'help_sheet.dart';
import 'keyboard_bar.dart';
import 'live_screen.dart';
import 'remote_view.dart';
import 'rfb_session.dart';

enum _Phase { loading, live, asleep, unreachable }

/// A bot's Linux computer, live and full screen: watch it, Take control (or
/// Teach), and give it back with I'm done. `go` is `control` or `teach` when
/// the screen is opened to start straight away.
class ComputerScreen extends ConsumerStatefulWidget {
  const ComputerScreen({super.key, required this.botId, this.go});

  final String botId;
  final String? go;

  @override
  ConsumerState<ComputerScreen> createState() => _ComputerScreenState();
}

class _ComputerScreenState extends ConsumerState<ComputerScreen> {
  late final ComputerApi _api = ComputerApi(ref.read(apiClientProvider));
  RfbSession? _session;
  RfbSession? _stale; // the dropped session, its last picture kept up while a new one connects
  Timer? _retry;
  int _tries = 0;
  StreamSubscription<Map<String, dynamic>>? _frames;
  _Phase _phase = _Phase.loading;
  bool _control = false;
  bool _teaching = false;
  bool _asking = false;
  bool _busy = false;
  bool _keyboard = false;
  bool _trackpad = false;
  bool _wokeOnce = false;
  bool _leaving = false;
  String? _error;
  OpenStuck? _card;
  RingMark? _ring;

  String get _name => ref.read(liveProvider).bots[widget.botId]?.name ?? 'the bot';

  @override
  void initState() {
    super.initState();
    _frames = ref.read(frameBusProvider).stream.listen(_onFrame);
    _boot();
  }

  @override
  void dispose() {
    _frames?.cancel();
    _retry?.cancel();
    _session?.dispose();
    _stale?.dispose();
    super.dispose();
  }

  void _onFrame(Map<String, dynamic> f) {
    if (f['type'] != 'computer_pointer' || f['bot_id'] != widget.botId) return;
    final x = f['x'], y = f['y'];
    if (x is! num || y is! num || !mounted) return;
    setState(() => _ring = RingMark(
        Offset(x.toDouble(), y.toDouble()), (_ring?.n ?? 0) + 1));
  }

  String _say(Object e) =>
      e is ApiException ? e.message : 'Something went wrong. Try again.';

  Future<void> _boot() async {
    try {
      var held = await _api.held(widget.botId);
      _teaching = await _api.teaching(widget.botId);
      _card = await _api.openStuck(widget.botId).catchError((_) => null);
      if (widget.go == 'teach' && !_teaching) {
        _teaching = await _api.startTeach(widget.botId);
        held = _teaching;
      } else if (widget.go == 'control' && !held) {
        held = await _api.takeControl(widget.botId);
      }
      if (!mounted) return;
      _connect(control: held);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _phase = _Phase.unreachable;
        _error = _say(e);
      });
    }
  }

  void _connect({required bool control}) {
    _session?.dispose();
    final channel = openLiveSocket(ref.read(socketOpenerProvider),
        ref.read(authProvider), widget.botId,
        control: control);
    final session = RfbSession(channel, controlling: control)
      ..addListener(_onSession);
    setState(() {
      _session = session;
      _control = control;
      _phase = _Phase.loading;
      _error = null;
    });
  }

  void _onSession() {
    final s = _session;
    if (s == null || !mounted) return;
    if (s.state == SessionState.live && _phase != _Phase.live) {
      _tries = 0;
      _dropStale();
      setState(() => _phase = _Phase.live);
    } else if (s.state == SessionState.closed) {
      _onClosed(s.closeCode);
    }
  }

  void _onClosed(int? code) {
    if (_control && (code == closeGivenBack || code == closeNotHeld)) {
      _leave(controlGivenBackText);
    } else if (code == closeAsleep) {
      if (_control && !_wokeOnce) {
        _wokeOnce = true;
        _wake();
      } else {
        setState(() => _phase = _Phase.asleep);
      }
    } else if (_tries < liveScreenRetries.length) {
      _keepPicture();
      _retry?.cancel();
      _retry = Timer(liveScreenRetries[_tries++], () {
        if (mounted) _connect(control: _control);
      });
    } else if (_phase != _Phase.unreachable) {
      _dropStale();
      setState(() {
        _phase = _Phase.unreachable;
        _error ??= droppedText(_name, code);
      });
    }
  }

  /// Owner, 2026-10-29: a dropped screen went black. Its last picture stays up while it reconnects.
  void _keepPicture() {
    final dropped = _session;
    if (dropped != null && _phase == _Phase.live) {
      dropped.removeListener(_onSession);
      _stale?.dispose();
      _stale = dropped;
      _session = null;
    }
    setState(() => _phase = _Phase.loading);
  }

  void _dropStale() {
    _stale?.dispose();
    _stale = null;
  }

  Future<void> _wake() async {
    try {
      await _api.wake(widget.botId);
      if (mounted) _connect(control: _control);
    } catch (e) {
      if (mounted) setState(() => _error = _say(e));
    }
  }

  void _leave(String? note) {
    if (_leaving || !mounted) return;
    _leaving = true;
    final messenger = ScaffoldMessenger.maybeOf(context);
    if (note != null) messenger?.showSnackBar(SnackBar(content: Text(note)));
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/');
    }
  }

  Future<void> _run(Future<String?> Function() job) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final note = await job();
      if (mounted) _leave(note);
    } catch (e) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = _say(e);
        });
      }
    }
  }

  Future<void> _take({required bool teach}) async {
    setState(() => _error = null);
    try {
      if (teach) {
        _teaching = await _api.startTeach(widget.botId);
      } else {
        await _api.takeControl(widget.botId);
      }
      if (mounted) _connect(control: true);
    } catch (e) {
      if (mounted) setState(() => _error = _say(e));
    }
  }

  Future<void> _giveBack(String? account, bool? keep) {
    final card = _card;
    return _run(() async {
      if (card != null) {
        await _api.clearStuck(card.id, account: account, keep: keep);
      } else {
        await _api.giveBack(widget.botId, account: account);
      }
      return null;
    });
  }

  Future<void> _stopTeach(String? description, {required bool discard}) =>
      _run(() async {
        final dropped = await _api.stopTeach(widget.botId,
            description: description, discard: discard);
        return dropped ? teachDiscardedText : teachProposedText;
      });

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        // While you hold control, Back asks first; otherwise it goes
        // to this bot's chat.
        if (_control && !_leaving) {
          setState(() => _asking = true);
        } else {
          goBack(context);
        }
      },
      child: Scaffold(
        // The phone's keyboard floats over the screen instead of squeezing it away.
        resizeToAvoidBottomInset: false,
        backgroundColor: Colors.black,
        appBar: AppBar(
          backgroundColor: Tokens.bg,
          title: Text("$_name's computer"),
          actions: [
            if (_control && _phase == _Phase.live)
              IconButton(
                tooltip: 'Keyboard',
                icon: Icon(_keyboard ? Icons.keyboard_hide : Icons.keyboard),
                onPressed: () => setState(() => _keyboard = !_keyboard),
              ),
            if (_control && _phase == _Phase.live)
              IconButton(
                key: const Key('trackpad-toggle'),
                tooltip: _trackpad ? 'Direct touch' : 'Trackpad',
                icon: Icon(_trackpad ? Icons.touch_app : Icons.mouse),
                onPressed: () => setState(() => _trackpad = !_trackpad),
              ),
            IconButton(
              tooltip: 'Help',
              icon: const Icon(Icons.help_outline),
              onPressed: () => showComputerHelp(context),
            ),
          ],
        ),
        body: Stack(children: [
          Column(children: [
            Expanded(child: _stage()),
            // Owner, 2026-11-05: a form in the bar (Which account did you use?) rises above the phone's
            // keyboard; the remote keyboard bar has its own place, so the bar stays put then.
            Padding(
              padding: EdgeInsets.only(
                  bottom: barLift(MediaQuery.viewInsetsOf(context).bottom, remoteKeys: _keyboard && _control)),
              child: Material(color: Tokens.panel, child: SafeArea(child: _bar())),
            ),
          ]),
          if (_keyboard && _control && _session != null)
            Positioned(
              left: 0,
              right: 0,
              bottom: MediaQuery.viewInsetsOf(context).bottom,
              child: KeyboardBar(
                onKey: _session!.tap,
                onHide: () => setState(() => _keyboard = false),
              ),
            ),
        ]),
      ),
    );
  }

  Widget _stage() {
    final session = _session;
    switch (_phase) {
      case _Phase.live:
        return RemoteView(
            session: session!,
            controlling: _control,
            ring: _ring,
            trackpad: _trackpad);
      case _Phase.asleep:
        return _centered("$_name's computer is asleep.",
            action: FilledButton(
                onPressed: _wake, child: const Text('Open it')));
      case _Phase.unreachable:
        return _centered(
            _error ?? "Can't reach $_name's screen.",
            action: OutlinedButton(
                onPressed: () {
                  _tries = 0;
                  setState(() {
                    _phase = _Phase.loading;
                    _error = null;
                  });
                  _boot();
                },
                child: const Text('Retry')));
      case _Phase.loading:
        final stale = _stale;
        if (stale == null) return const Center(child: CircularProgressIndicator());
        return Stack(children: [
          Positioned.fill(
              child: RemoteView(
                  session: stale, controlling: false, ring: _ring, trackpad: _trackpad)),
          const Positioned(top: Tokens.space2, left: 0, right: 0, child: Center(child: _Reconnecting())),
        ]);
    }
  }

  Widget _centered(String text, {required Widget action}) => Center(
        child: Padding(
          padding: const EdgeInsets.all(Tokens.space6),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(text,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Tokens.textSecondary)),
            const SizedBox(height: Tokens.space3),
            action,
          ]),
        ),
      );

  Widget _bar() {
    final pad = const EdgeInsets.all(Tokens.space3);
    if (_asking && _control) return Padding(padding: pad, child: _form());
    if (_control) {
      return Padding(
        padding: pad,
        child: Row(children: [
          Expanded(
            child: Text(
                _teaching
                    ? "You're teaching $_name. Clicks and field names are recorded, never what you type."
                    : "You're in control",
                style: const TextStyle(color: Tokens.textSecondary)),
          ),
          const SizedBox(width: Tokens.space3),
          FilledButton(
              // The theme's buttons fill the width; here it sits beside the line.
              style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
              onPressed: () => setState(() => _asking = true),
              child: Text(_teaching ? "I'm done teaching" : "I'm done")),
        ]),
      );
    }
    return Padding(
      padding: pad,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        if (_error != null && _phase == _Phase.live)
          Padding(
            padding: const EdgeInsets.only(bottom: Tokens.space2),
            child: Text(_error!,
                style: const TextStyle(color: Tokens.dangerText)),
          ),
        Row(children: [
          Expanded(
            child: FilledButton(
                onPressed:
                    _phase == _Phase.live ? () => _take(teach: false) : null,
                child: const Text('Take control')),
          ),
          const SizedBox(width: Tokens.space2),
          Expanded(
            child: OutlinedButton(
                onPressed:
                    _phase == _Phase.live ? () => _take(teach: true) : null,
                child: const Text('Teach')),
          ),
        ]),
      ]),
    );
  }

  Widget _form() {
    if (_teaching) {
      return TeachDoneForm(
        busy: _busy,
        error: _error,
        onConfirm: (d) => _stopTeach(d, discard: false),
        onDiscard: () => _stopTeach(null, discard: true),
        onBack: () => setState(() {
          _asking = false;
          _error = null;
        }),
      );
    }
    return GiveBackForm(
      host: _card?.host,
      signIn: _card?.signIn ?? false,
      busy: _busy,
      error: _error,
      onConfirm: _giveBack,
      onBack: () => setState(() {
        _asking = false;
        _error = null;
      }),
    );
  }
}

/// Why the screen is unreachable after its retries: the close code helps tell what dropped it.
String droppedText(String name, int? code) =>
    "Can't reach $name's screen${code == null ? '' : ' (closed: $code)'}.";

class _Reconnecting extends StatelessWidget {
  const _Reconnecting();

  @override
  Widget build(BuildContext context) => DecoratedBox(
        decoration: BoxDecoration(
            color: Tokens.panel, borderRadius: BorderRadius.circular(Tokens.radiusLg)),
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: Tokens.space3, vertical: Tokens.space2),
          child: Text('Reconnecting…', style: TextStyle(color: Tokens.textSecondary)),
        ),
      );
}

/// How far the bottom bar rises: by the phone's keyboard, unless the remote
/// computer's keyboard bar is what you are typing into.
double barLift(double keyboard, {required bool remoteKeys}) => remoteKeys ? 0 : keyboard;
