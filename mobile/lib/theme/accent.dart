import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import 'tokens.dart';

/// The chosen accent's shades, carried by the theme so every screen picks up
/// a new choice at once.
@immutable
class AccentColors extends ThemeExtension<AccentColors> {
  const AccentColors({
    required this.accent,
    required this.strong,
    required this.soft,
    required this.tint,
  });

  factory AccentColors.from(AccentChoice c) =>
      AccentColors(accent: c.accent, strong: c.strong, soft: c.soft, tint: c.tint);

  final Color accent;
  final Color strong;
  final Color soft;
  final Color tint;

  static final _fallback = AccentColors.from(Tokens.accents.first);

  static AccentColors of(BuildContext context) =>
      Theme.of(context).extension<AccentColors>() ?? _fallback;

  @override
  AccentColors copyWith(
          {Color? accent, Color? strong, Color? soft, Color? tint}) =>
      AccentColors(
        accent: accent ?? this.accent,
        strong: strong ?? this.strong,
        soft: soft ?? this.soft,
        tint: tint ?? this.tint,
      );

  @override
  AccentColors lerp(AccentColors? other, double t) {
    if (other == null) return this;
    return AccentColors(
      accent: Color.lerp(accent, other.accent, t)!,
      strong: Color.lerp(strong, other.strong, t)!,
      soft: Color.lerp(soft, other.soft, t)!,
      tint: Color.lerp(tint, other.tint, t)!,
    );
  }
}

AccentChoice accentById(String? id) => Tokens.accents.firstWhere(
      (a) => a.id == id,
      orElse: () => Tokens.accents.first,
    );

/// The accent the user picked in Settings, kept on the phone.
class AccentController extends Notifier<AccentChoice> {
  @override
  AccentChoice build() {
    _load();
    return Tokens.accents.first;
  }

  Future<void> _load() async {
    final id = await ref.read(sessionStoreProvider).readAccent();
    if (id != null) state = accentById(id);
  }

  Future<void> choose(AccentChoice choice) async {
    state = choice;
    await ref.read(sessionStoreProvider).writeAccent(choice.id);
  }
}

final accentProvider =
    NotifierProvider<AccentController, AccentChoice>(AccentController.new);
