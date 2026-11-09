import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme/accent.dart';
import '../theme/tokens.dart';
import '../widgets/lens_specs.dart';
import '../widgets/lensbot.dart';

/// Pick a Lensbot shape, a colour and a role. A picture upload comes later.
class AvatarEditor extends StatelessWidget {
  const AvatarEditor({
    super.key,
    required this.avatar,
    required this.onChanged,
    this.star = false,
  });

  final Avatar avatar;
  final bool star;
  final ValueChanged<Avatar> onChanged;

  @override
  Widget build(BuildContext context) {
    final shape = lensbotShape(avatar.shape);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Center(child: LensbotAvatar(avatar: avatar, size: 96, star: star)),
      const SizedBox(height: Tokens.space3),
      const Text('Shape', style: TextStyle(color: Tokens.textSecondary)),
      const SizedBox(height: Tokens.space2),
      Wrap(spacing: Tokens.space2, runSpacing: Tokens.space2, children: [
        for (final s in lensSpecs)
          _Tile(
            selected: s.id == shape,
            label: s.label,
            onTap: () => onChanged(avatar.copyWith(shape: s.id)),
            child: LensbotAvatar(
                avatar: avatar.copyWith(shape: s.id), size: 48),
          ),
      ]),
      const SizedBox(height: Tokens.space3),
      const Text('Colour', style: TextStyle(color: Tokens.textSecondary)),
      const SizedBox(height: Tokens.space2),
      Wrap(spacing: Tokens.space2, runSpacing: Tokens.space2, children: [
        for (final (hex, name) in robotColours)
          Semantics(
            label: name,
            button: true,
            child: GestureDetector(
              onTap: () => onChanged(avatar.copyWith(color: hex)),
              child: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Avatar(color: hex).colour,
                  border: Border.all(
                    color: avatar.color.toLowerCase() == hex
                        ? AccentColors.of(context).strong
                        : Tokens.border,
                    width: avatar.color.toLowerCase() == hex ? 3 : 1,
                  ),
                ),
              ),
            ),
          ),
      ]),
      const SizedBox(height: Tokens.space3),
      const Text('Role', style: TextStyle(color: Tokens.textSecondary)),
      const SizedBox(height: Tokens.space2),
      Wrap(spacing: Tokens.space2, children: [
        for (final r in botRoles)
          ChoiceChip(
            label: Text(roleLabels[r]!),
            selected: (avatar.role ?? 'general') == r,
            onSelected: (_) => onChanged(avatar.copyWith(role: r)),
          ),
      ]),
    ]);
  }
}

class _Tile extends StatelessWidget {
  const _Tile({
    required this.selected,
    required this.label,
    required this.onTap,
    required this.child,
  });

  final bool selected;
  final String label;
  final VoidCallback onTap;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      button: true,
      selected: selected,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(Tokens.space1),
          decoration: BoxDecoration(
            color: Tokens.raised,
            borderRadius: BorderRadius.circular(Tokens.radiusSm),
            border: Border.all(
                color: selected ? AccentColors.of(context).strong : Tokens.border,
                width: selected ? 2 : 1),
          ),
          child: child,
        ),
      ),
    );
  }
}
