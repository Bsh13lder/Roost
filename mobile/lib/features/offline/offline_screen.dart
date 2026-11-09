import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../api/reachability.dart';
import '../../board/tasks/offline/offline_tasks_screen.dart';
import '../../theme/tokens.dart';
import '../../api/models.dart';
import '../../theme/accent.dart';
import '../../widgets/lensbot.dart';

const _botSize = 72.0;
const offlineTitle = "Can't reach your Roost";
const offlineLine =
    'Your Mac needs to be on and awake, with Tailscale connected.';

/// Shown over wherever you were when the gateway stops answering. It asks
/// again every [offlineRetryInterval] and steps aside once Roost answers.
class OfflineScreen extends ConsumerStatefulWidget {
  const OfflineScreen({super.key});

  @override
  ConsumerState<OfflineScreen> createState() => _OfflineScreenState();
}

class _OfflineScreenState extends ConsumerState<OfflineScreen> {
  Timer? _timer;
  bool _checking = false;
  bool _left = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(offlineRetryInterval, (_) => _check());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _check() async {
    if (_checking) return;
    setState(() => _checking = true);
    await ref.read(offlineProvider.notifier).probe();
    if (mounted) setState(() => _checking = false);
  }

  /// Leaves once Roost answers, but only while this screen is on top, so a
  /// Settings screen opened from here is never closed under you.
  void _leaveWhenBack(bool offline) {
    final current = ModalRoute.of(context)?.isCurrent ?? false;
    if (offline || !current || _left) return;
    _left = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // Opened at start, the offline screen may be the only page: go home.
      if (context.canPop()) {
        context.pop();
      } else {
        context.go('/');
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    _leaveWhenBack(ref.watch(offlineProvider));
    return PopScope(
      canPop: false,
      child: Scaffold(
        body: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(Tokens.space6),
              child: _body(),
            ),
          ),
        ),
      ),
    );
  }

  Widget _body() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // A sleeping Lensbot in your accent: calm, never an error red.
        SizedBox(
          width: _botSize,
          height: _botSize,
          child: CustomPaint(
            painter: LensbotPainter(AccentColors.of(context).accent,
                status: BotStatus.offDuty),
          ),
        ),
        const SizedBox(height: Tokens.space6),
        const Text(offlineTitle,
            textAlign: TextAlign.center,
            style: TextStyle(
                fontSize: Tokens.fsTitle, fontWeight: FontWeight.w600)),
        const SizedBox(height: Tokens.space2),
        const Text(offlineLine,
            textAlign: TextAlign.center,
            style: TextStyle(color: Tokens.textSecondary)),
        const SizedBox(height: Tokens.space6),
        FilledButton(
          key: const Key('offline-try-again'),
          onPressed: _checking ? null : _check,
          child: Text(_checking ? 'Checking…' : 'Try again'),
        ),
        const SizedBox(height: Tokens.space2),
        // Tasks work with no connection (offline tasks, O1).
        OutlinedButton(
          key: const Key('offline-open-tasks'),
          onPressed: () => context.push(offlineTasksPath),
          child: const Text('Open my tasks'),
        ),
        const SizedBox(height: Tokens.space2),
        TextButton(
          key: const Key('offline-settings'),
          onPressed: () => context.push('/settings'),
          child: const Text('Settings'),
        ),
      ],
    );
  }
}
