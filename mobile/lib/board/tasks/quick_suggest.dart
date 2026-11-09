// The quick line's suggestions, ported from the web's quickSuggest.ts. Pure:
// which token is being typed at the caret, and what could finish it. Only
// names from lists the app already loads are offered; the server then reads
// the accepted text, so the line means exactly what the server says.

/// The most suggestions shown at once.
const maxSuggestions = 6;

/// A project or bot name of up to this many words completes across spaces.
const maxTokenWords = 5;

class SuggestOption {
  const SuggestOption(this.key, this.label, this.insert, [this.hint]);

  final String key;
  final String label;

  /// The whole token, trigger included: "/Casa Nueva".
  final String insert;
  final String? hint;
}

class Suggestion {
  const Suggestion(this.trigger, this.start, this.end, this.options);

  final String trigger;
  final int start;
  final int end;
  final List<SuggestOption> options;
}

class SuggestSources {
  const SuggestSources({
    this.projects = const [],
    this.tags = const [],
    this.bots = const [],
  });

  final List<String> projects;
  final List<String> tags;
  final List<String> bots;

  List<String> namesFor(String trigger) => switch (trigger) {
        '/' => projects,
        '#' => tags,
        _ => bots,
      };
}

class _Level {
  const _Level(this.option, this.aliases);
  final SuggestOption option;
  final List<String> aliases;
}

const _levels = [
  _Level(SuggestOption('urgent', 'Urgent', '!urgent', '!!!'), ['!!', 'urgente']),
  _Level(SuggestOption('high', 'High', '!high', '!!'), ['!', 'alta']),
  _Level(SuggestOption('medium', 'Medium', '!medium', '!'), ['media']),
  _Level(SuggestOption('low', 'Low', '!low', '!-'), ['-', 'baja']),
  _Level(SuggestOption('star', 'Star it', '!star', '*'), ['fav']),
];
const _triggers = {'/', '#', '@', '!'};
final _shorthand = RegExp(r'^(?:!{2,}|!-)$');
final _space = RegExp(r'\s');

bool _startsLike(String name, String query) =>
    name.toLowerCase().startsWith(query.toLowerCase());

/// The token at [caret]: the nearest / # @ or ! that starts a word before it.
({String trigger, int start, String query})? tokenAt(String text, int caret) {
  final before = text.substring(0, caret.clamp(0, text.length));
  for (var i = before.length - 1; i >= 0; i--) {
    final char = before[i];
    if (!_triggers.contains(char)) continue;
    if (i > 0 && !_space.hasMatch(before[i - 1])) continue;
    final query = before.substring(i + 1);
    if ((char == '!' || char == '#') && _space.hasMatch(query)) return null;
    final words = query.trim().split(_space).where((w) => w.isNotEmpty);
    if (words.length > maxTokenWords) return null;
    return (trigger: char, start: i, query: query);
  }
  return null;
}

List<SuggestOption> _levelOptions(String query) => [
      for (final l in _levels)
        if ([l.option.key, ...l.aliases].any((w) => _startsLike(w, query)))
          l.option,
    ];

List<SuggestOption> _nameOptions(List<String> names, String trigger, String query) => [
      for (final n in names)
        if (_startsLike(n, query)) SuggestOption(n, n, '$trigger$n'),
    ];

/// What could finish the token at [caret], or null.
Suggestion? suggest(String text, int caret, SuggestSources sources) {
  final token = tokenAt(text, caret);
  if (token == null) return null;
  final typed = text.substring(token.start, caret);
  if (token.trigger == '!' && _shorthand.hasMatch(typed)) return null;
  final found = token.trigger == '!'
      ? _levelOptions(token.query)
      : _nameOptions(sources.namesFor(token.trigger), token.trigger, token.query);
  final options = found.take(maxSuggestions).toList(growable: false);
  if (options.isEmpty) return null;
  if (options.length == 1 && options.first.insert.toLowerCase() == typed.toLowerCase()) {
    return null;
  }
  return Suggestion(token.trigger, token.start, caret, options);
}

/// The text with the typed token replaced by [option], one space after it,
/// and where the caret goes.
({String text, int caret}) acceptSuggestion(
    String text, Suggestion s, SuggestOption option) {
  final after = text.substring(s.end);
  final head = '${text.substring(0, s.start)}${option.insert}';
  return (
    text: '$head${after.startsWith(' ') ? '' : ' '}$after',
    caret: head.length + 1,
  );
}
