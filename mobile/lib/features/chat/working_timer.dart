import 'dart:async';

import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import 'on_it_lead.dart';

const _tick = Duration(seconds: 1);

/// How long the bot has been at it ("12s"), rewritten once a second.
class WorkingTimer extends StatefulWidget {
  const WorkingTimer({super.key, required this.since});

  final DateTime since;

  @override
  State<WorkingTimer> createState() => _WorkingTimerState();
}

class _WorkingTimerState extends State<WorkingTimer> {
  late final Timer _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(_tick, (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Text(
        formatElapsed(DateTime.now().difference(widget.since)),
        key: const Key('working-timer'),
        style: const TextStyle(
          color: Tokens.textFaint,
          fontSize: Tokens.fsCaption,
          fontFeatures: [FontFeature.tabularFigures()],
        ),
      );
}
