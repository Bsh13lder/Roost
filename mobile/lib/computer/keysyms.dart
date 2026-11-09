/// X11 keysyms for the keys the app sends. A typed character maps to its own
/// code (Latin-1) or the Unicode keysym; nothing here remembers what was typed.
const keyBackspace = 0xFF08;
const keyTab = 0xFF09;
const keyReturn = 0xFF0D;
const keyEscape = 0xFF1B;
const keyLeft = 0xFF51;
const keyUp = 0xFF52;
const keyRight = 0xFF53;
const keyDown = 0xFF54;

int keysymForRune(int rune) {
  if (rune == 0x0A || rune == 0x0D) return keyReturn;
  if (rune == 0x09) return keyTab;
  if (rune < 0x20 || (rune >= 0x7F && rune < 0xA0)) return 0;
  if (rune < 0x100) return rune;
  return 0x01000000 + rune;
}

/// What a text field edit means as key presses: backspaces for what went
/// away, then the new characters. Works on the common prefix of old and new.
({int backspaces, List<int> keysyms}) diffToKeys(String before, String after) {
  final a = before.runes.toList(), b = after.runes.toList();
  var common = 0;
  while (common < a.length && common < b.length && a[common] == b[common]) {
    common++;
  }
  final keys = <int>[
    for (final rune in b.skip(common))
      if (keysymForRune(rune) != 0) keysymForRune(rune),
  ];
  return (backspaces: a.length - common, keysyms: keys);
}
