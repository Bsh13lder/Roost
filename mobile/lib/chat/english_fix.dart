/// Correct my English: the `english_fix` line the server posts under a spoken
/// message when the bot's voice has "Correct my English" on. Pure: it reads
/// the line's JSON and turns it into the parts a screen draws. Mirrors
/// web/src/lib/englishFix.ts.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';

/// One correction: the words you said and the words that should be there.
@immutable
class WordFix {
  const WordFix(this.wrong, this.right);

  final String wrong;
  final String right;

  @override
  bool operator ==(Object other) =>
      other is WordFix && other.wrong == wrong && other.right == right;

  @override
  int get hashCode => Object.hash(wrong, right);

  @override
  String toString() => 'WordFix($wrong → $right)';
}

/// The line's body: which message it corrects, what you said, the corrected
/// sentence and the fixes.
@immutable
class EnglishFix {
  const EnglishFix({
    required this.messageId,
    required this.said,
    required this.corrected,
    required this.fixes,
  });

  final String messageId;
  final String said;
  final String corrected;
  final List<WordFix> fixes;
}

/// An `english_fix` body, or null when it cannot be read. A fix that is not
/// two strings is skipped; a missing `fixes` is none.
EnglishFix? parseEnglishFix(String body) {
  Object? decoded;
  try {
    decoded = jsonDecode(body);
  } on FormatException {
    return null;
  }
  if (decoded is! Map) return null;
  final said = decoded['said'];
  final corrected = decoded['corrected'];
  if (said is! String || corrected is! String) return null;
  final id = decoded['message_id'];
  final raw = decoded['fixes'];
  return EnglishFix(
    messageId: id is String ? id : '',
    said: said,
    corrected: corrected,
    fixes: [
      for (final f in (raw is List ? raw : const []))
        if (f is Map && f['wrong'] is String && f['right'] is String)
          WordFix(f['wrong'] as String, f['right'] as String),
    ],
  );
}

/// How a piece of the shown sentence is drawn.
enum FixPart { plain, wrong, right }

@immutable
class FixSegment {
  const FixSegment(this.kind, this.text);

  final FixPart kind;
  final String text;
}

/// What a screen draws: the corrected sentence in pieces, with each placed fix
/// as its wrong words (struck through) followed by its right words, and the
/// fixes that could not be placed, to list at the end as "wrong → right".
@immutable
class ShownFix {
  const ShownFix(this.segments, this.unplaced);

  final List<FixSegment> segments;
  final List<WordFix> unplaced;
}

/// Places each fix in the corrected sentence, in order. A fix is placed only
/// when its wrong words are in what you said and its right words are found in
/// the corrected sentence after the last placed fix; anything else is listed
/// at the end instead, so nothing is ever lost.
ShownFix fixSegments(EnglishFix fix) {
  final segments = <FixSegment>[];
  final unplaced = <WordFix>[];
  final text = fix.corrected;
  var cursor = 0;
  for (final f in fix.fixes) {
    final at = _placeOf(fix.said, text, f, cursor);
    if (at == null) {
      unplaced.add(f);
      continue;
    }
    if (at > cursor) segments.add(FixSegment(FixPart.plain, text.substring(cursor, at)));
    segments.add(FixSegment(FixPart.wrong, f.wrong));
    segments.add(FixSegment(FixPart.right, text.substring(at, at + f.right.length)));
    cursor = at + f.right.length;
  }
  if (cursor < text.length || segments.isEmpty) {
    segments.add(FixSegment(FixPart.plain, text.substring(cursor)));
  }
  return ShownFix(List.unmodifiable(segments), List.unmodifiable(unplaced));
}

/// Where [f.right] starts in [corrected] at or after [from], or null when the
/// fix cannot be placed.
int? _placeOf(String said, String corrected, WordFix f, int from) {
  if (f.wrong.trim().isEmpty || f.right.trim().isEmpty) return null;
  if (_find(said, f.wrong, 0) == null) return null;
  return _find(corrected, f.right, from);
}

/// [needle] in [hay] from [from]: whole words first, then whole words ignoring
/// case, then anywhere; null when it is not there.
int? _find(String hay, String needle, int from) {
  if (from >= hay.length) return null;
  final rest = hay.substring(from);
  final word = RegExp('(?<![\\p{L}\\p{N}])${RegExp.escape(needle)}(?![\\p{L}\\p{N}])', unicode: true);
  final loose = RegExp('(?<![\\p{L}\\p{N}])${RegExp.escape(needle)}(?![\\p{L}\\p{N}])',
      unicode: true, caseSensitive: false);
  final at = word.firstMatch(rest)?.start ?? loose.firstMatch(rest)?.start ?? rest.indexOf(needle);
  return at < 0 ? null : from + at;
}

/// "went → goes"; a word to drop reads "am → (drop it)".
String arrowLine(WordFix f) => '${f.wrong} → ${f.right.trim().isEmpty ? '(drop it)' : f.right}';
