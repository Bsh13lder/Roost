import 'package:flutter/material.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';

/// A round-cornered square check, filled with the accent once done.
class RoundCheck extends StatelessWidget {
  const RoundCheck({
    super.key,
    required this.done,
    required this.onTap,
    this.urgent = false,
  });

  final bool done;
  final bool urgent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context).accent;
    return Semantics(
      checked: done,
      button: true,
      child: InkResponse(
        onTap: onTap,
        radius: Tokens.space6,
        child: Padding(
          padding: const EdgeInsets.all(Tokens.space3),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            width: 22,
            height: 22,
            decoration: BoxDecoration(
              color: done ? accent : Colors.transparent,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(
                color: done
                    ? accent
                    : urgent
                        ? Tokens.warn
                        : Tokens.borderStrong,
                width: 1.5,
              ),
            ),
            child: done
                ? const Icon(Icons.check, size: 16, color: Tokens.onAccent)
                : null,
          ),
        ),
      ),
    );
  }
}
