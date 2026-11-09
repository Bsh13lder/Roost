import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// A priority's colour, Todoist-like: urgent red, high orange, medium and low grey (the default stays calm).
Color priorityTone(String priority) => switch (priority) {
      'urgent' => Tokens.prioUrgent,
      'high' => Tokens.prioHigh,
      'medium' => Tokens.prioLow,
      _ => Tokens.prioLow,
    };

String _priorityWords(String p) => switch (p) {
      'urgent' => 'urgent',
      'high' => 'high priority',
      'medium' => 'medium priority',
      _ => 'low priority',
    };

/// Todoist's round check: the ring and a faint fill in the priority's
/// colour. A tap fills it with a tick, gives a small pop, then reports.
class TodoCheck extends StatefulWidget {
  const TodoCheck({
    super.key,
    required this.priority,
    required this.done,
    required this.onChanged,
  });

  final String priority;
  final bool done;
  final VoidCallback onChanged;

  @override
  State<TodoCheck> createState() => _TodoCheckState();
}

class _TodoCheckState extends State<TodoCheck>
    with SingleTickerProviderStateMixin {
  late final _pop = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 260),
  );
  bool _ticked = false;

  @override
  void dispose() {
    _pop.dispose();
    super.dispose();
  }

  Future<void> _tap() async {
    if (widget.done) return widget.onChanged();
    setState(() => _ticked = true);
    await _pop.forward(from: 0);
    if (!mounted) return;
    widget.onChanged();
    setState(() => _ticked = false);
  }

  @override
  Widget build(BuildContext context) {
    final tone = priorityTone(widget.priority);
    final filled = widget.done || _ticked;
    final ease = CurveTween(curve: Curves.easeOut);
    return Semantics(
      checked: widget.done,
      button: true,
      label: _priorityWords(widget.priority),
      child: InkResponse(
        onTap: _tap,
        radius: Tokens.space5,
        child: Padding(
          padding: const EdgeInsets.all(Tokens.space2),
          child: ScaleTransition(
            scale: _pop.drive(TweenSequence([
              TweenSequenceItem(
                  tween: Tween(begin: 1.0, end: 1.18).chain(ease), weight: 1),
              TweenSequenceItem(
                  tween: Tween(begin: 1.18, end: 1.0).chain(ease), weight: 1),
            ])),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              width: Tokens.checkSize,
              height: Tokens.checkSize,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: filled ? tone : tone.withAlpha(Tokens.ringFillAlpha),
                border: Border.all(color: tone, width: 1.6),
              ),
              child: filled
                  ? const Icon(Icons.check, size: 14, color: Tokens.bg)
                  : null,
            ),
          ),
        ),
      ),
    );
  }
}
