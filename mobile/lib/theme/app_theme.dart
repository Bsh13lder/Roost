import 'package:flutter/material.dart';

import 'accent.dart';
import 'tokens.dart';

/// The app's one theme, built around the accent the user picked.
ThemeData buildTheme([AccentChoice? choice]) {
  final accent = choice ?? Tokens.accents.first;
  final scheme = ColorScheme.dark(
    primary: accent.accent,
    onPrimary: Tokens.onAccent,
    secondary: accent.strong,
    // A selected chip, segment or nav indicator: soft accent text on the
    // tint. Left unset, Material draws black text there (unreadable).
    secondaryContainer: accent.tint,
    onSecondaryContainer: accent.soft,
    primaryContainer: accent.tint,
    onPrimaryContainer: accent.soft,
    surface: Tokens.panel,
    onSurface: Tokens.text,
    error: Tokens.danger,
  );
  final border = OutlineInputBorder(
    borderRadius: BorderRadius.circular(Tokens.radiusMd),
    borderSide: const BorderSide(color: Tokens.border),
  );
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    extensions: [AccentColors.from(accent)],
    scaffoldBackgroundColor: Tokens.bg,
    canvasColor: Tokens.bg,
    dividerColor: Tokens.border,
    // Undo was white on light grey: a dark bar with the accent's action.
    snackBarTheme: SnackBarThemeData(
      backgroundColor: Tokens.raised,
      contentTextStyle: const TextStyle(color: Tokens.text),
      actionTextColor: accent.soft,
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: Tokens.overlay,
      modalBackgroundColor: Tokens.overlay,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Tokens.raised,
      border: border,
      enabledBorder: border,
      focusedBorder: border.copyWith(
        borderSide: BorderSide(color: accent.strong),
      ),
      hintStyle: const TextStyle(color: Tokens.textFaint),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: accent.accent,
        foregroundColor: Tokens.onAccent,
        minimumSize: const Size.fromHeight(48),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Tokens.radiusMd),
        ),
      ),
    ),
  );
}
