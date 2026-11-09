import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// One rounded card of rows with thin inset lines between them, an optional
/// small label above and a one-line caption below (the profile, Settings).
class GroupedCard extends StatelessWidget {
  const GroupedCard({
    super.key,
    required this.children,
    this.label,
    this.caption,
  });

  final List<Widget> children;
  final String? label;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: Tokens.space4, vertical: Tokens.space2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (label != null) _Label(label!),
          DecoratedBox(
            decoration: BoxDecoration(
              color: Tokens.panel,
              borderRadius: BorderRadius.circular(Tokens.radiusLg),
              border: Border.all(color: Tokens.border),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(Tokens.radiusLg),
              child: Column(children: _withLines(children)),
            ),
          ),
          if (caption != null) _Caption(caption!),
        ],
      ),
    );
  }

  static List<Widget> _withLines(List<Widget> rows) => [
        for (var i = 0; i < rows.length; i++) ...[
          if (i > 0)
            const Divider(
                height: 1, thickness: 1, indent: 56, color: Tokens.border),
          rows[i],
        ],
      ];
}

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(
            Tokens.space4, Tokens.space2, Tokens.space4, Tokens.space2),
        child: Text(text,
            style: const TextStyle(
                fontSize: Tokens.fsLabel, color: Tokens.textFaint)),
      );
}

class _Caption extends StatelessWidget {
  const _Caption(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(
            Tokens.space4, Tokens.space2, Tokens.space4, 0),
        child: Text(text,
            style: const TextStyle(
                fontSize: Tokens.fsLabel, color: Tokens.textFaint)),
      );
}

/// A row that opens a page: an icon, the label, a quiet value and a chevron.
class NavRow extends StatelessWidget {
  const NavRow({
    super.key,
    required this.label,
    this.icon,
    this.value,
    this.onTap,
    this.danger = false,
  });

  final String label;
  final IconData? icon;
  final String? value;
  final VoidCallback? onTap;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final color = danger ? Tokens.dangerText : Tokens.text;
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 56),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
          child: Row(children: [
            if (icon != null) ...[
              Icon(icon, size: 22, color: danger ? color : Tokens.textSecondary),
              const SizedBox(width: Tokens.space4),
            ],
            Expanded(
              child: Text(label,
                  style: TextStyle(fontSize: Tokens.fsLead, color: color)),
            ),
            if (value != null && value!.isNotEmpty)
              Flexible(
                child: Text(value!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: Tokens.fsLead, color: Tokens.textSecondary)),
              ),
            if (onTap != null && !danger) ...[
              const SizedBox(width: Tokens.space2),
              const Icon(Icons.chevron_right, color: Tokens.textFaint, size: 22),
            ],
          ]),
        ),
      ),
    );
  }
}

/// A row with a label, an optional caption under it and a switch.
class SwitchRow extends StatelessWidget {
  const SwitchRow({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
    this.caption,
    this.switchKey,
  });

  final String label;
  final String? caption;
  final bool value;
  final ValueChanged<bool>? onChanged;
  final Key? switchKey;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: Tokens.space4, vertical: Tokens.space3),
      child: Row(children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: const TextStyle(fontSize: Tokens.fsLead)),
              if (caption != null)
                Text(caption!,
                    style: const TextStyle(
                        fontSize: Tokens.fsLabel,
                        color: Tokens.textSecondary)),
            ],
          ),
        ),
        Switch(key: switchKey, value: value, onChanged: onChanged),
      ]),
    );
  }
}

/// Free content inside a [GroupedCard], padded like a row.
class CardBody extends StatelessWidget {
  const CardBody({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(Tokens.space4),
        child: SizedBox(width: double.infinity, child: child),
      );
}
