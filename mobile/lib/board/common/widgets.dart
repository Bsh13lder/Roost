import 'package:flutter/material.dart';

import '../../api/api_error.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';

String errorText(Object e) =>
    e is ApiException ? e.message : 'Something went wrong. Try again.';

/// A quiet centred line: empty, loading or error state.
class BoardNote extends StatelessWidget {
  const BoardNote(this.text, {super.key, this.error = false});

  final String text;
  final bool error;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(Tokens.space6),
        child: Center(
          child: Text(
            text,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: error ? Tokens.dangerText : Tokens.textSecondary,
              fontSize: Tokens.fsBody,
            ),
          ),
        ),
      );
}

/// A meter drawn from the server's percent and tone (never worked out here).
class ToneBar extends StatelessWidget {
  const ToneBar({super.key, required this.percent, this.tone});

  final num? percent;
  final String? tone;

  @override
  Widget build(BuildContext context) {
    final color = switch (tone) {
      'over' => Tokens.danger,
      'warn' => Tokens.warn,
      _ => AccentColors.of(context).accent,
    };
    final value = (percent ?? 0).clamp(0, 100) / 100;
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: LinearProgressIndicator(
        value: value.toDouble(),
        minHeight: 6,
        color: color,
        backgroundColor: Tokens.raised,
      ),
    );
  }
}

/// Parses a `#RRGGBB` colour from the server; falls back to the accent.
Color hexColor(String? hex) {
  final h = (hex ?? '').replaceFirst('#', '');
  final v = int.tryParse(h.length == 6 ? 'FF$h' : h, radix: 16);
  return v == null ? Tokens.accent : Color(v);
}

void snack(BuildContext context, String text,
    {String? action, VoidCallback? onAction}) {
  final m = ScaffoldMessenger.maybeOf(context);
  m?.hideCurrentSnackBar();
  m?.showSnackBar(SnackBar(
    content: Text(text),
    persist: false, // Flutter keeps a bar with an action until tapped
    action: action == null
        ? null
        : SnackBarAction(label: action, onPressed: onAction ?? () {}),
  ));
}

/// A section title line with an optional trailing widget.
class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing});

  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(
            Tokens.space4, Tokens.space4, Tokens.space4, Tokens.space2),
        child: Row(children: [
          Expanded(
            child: Text(text,
                style: const TextStyle(
                    color: Tokens.textSecondary,
                    fontSize: Tokens.fsLabel,
                    fontWeight: FontWeight.w600)),
          ),
          ?trailing,
        ]),
      );
}
