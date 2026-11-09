// Cancelling a chip (ported from the web's quickKept.ts): its typed words go
// back into the title as plain text and are not read again while you keep
// typing. The server does the keeping (`keep` on POST /api/tasks/parse);
// this is the phone's side. Pure.

bool _same(String a, String b) => a.toLowerCase() == b.toLowerCase();

/// The kept words still in the text, so deleting one and typing it anew
/// reads it again.
List<String> stillTyped(List<String> kept, String text) {
  final lower = text.toLowerCase();
  return [for (final w in kept) if (lower.contains(w.toLowerCase())) w];
}

/// [kept] plus a chip's [words], once each.
List<String> keepWords(List<String> kept, List<String> words) => [
      ...kept,
      for (final w in words)
        if (!kept.any((have) => _same(have, w))) w,
    ];

/// A chip whose words were all cancelled hides at once, before the server
/// answers.
bool isCancelled(List<String> words, List<String> kept) =>
    words.isNotEmpty && words.every((w) => kept.any((have) => _same(have, w)));
