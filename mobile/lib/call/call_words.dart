/// Words that end a call when they are the whole of what you said (shared
/// contract D; the web's web/src/lib/callWords.ts holds the same set). A
/// goodbye is never sent as a message. Never a substring match: "bye the
/// way, add eggs" is just words.
library;

const goodbyeWords = {
  'bye',
  'goodbye',
  'bye bye',
  'hang up',
  'end call',
  'end the call',
  "that's all",
  'that is all',
  'adiós',
  'adios',
  'hasta luego',
  'cuelga',
  'chao',
};

final _punctuation = RegExp(r'''[.,!?¡¿;:"“”…]+''');
final _spaces = RegExp(r'\s+');

/// True only when the whole utterance, lower-cased, trimmed and with its
/// punctuation stripped, is one of [goodbyeWords].
bool isGoodbye(String text) {
  final plain = text
      .toLowerCase()
      .replaceAll('’', "'")
      .replaceAll(_punctuation, ' ')
      .replaceAll(_spaces, ' ')
      .trim();
  return plain.isNotEmpty && goodbyeWords.contains(plain);
}
