/// A bot's reply opens with one line of what it is starting on ("On it:
/// checking your inbox.", roost/talk/chat_feel.py). Owner, 2026-10-27: that
/// line is the working robot's words while the bot works, never a line of the
/// answer. Mirrors web/src/lib/onItLead.ts: while only the lead has streamed it
/// is the working line; once the answer follows only the answer shows; a reply
/// that is nothing but the lead keeps its words.
library;

final _lead = RegExp(r'^\s*On it\s*[:,—-]\s*([^\n]*)(?:\n+|$)', caseSensitive: false);

/// What the working line says when the bot has not said yet.
const workingDefaultWords = 'reading your message';

class OnItSplit {
  const OnItSplit(this.lead, this.rest);

  /// The words after "On it:", or null when the reply has no such line.
  final String? lead;

  /// The answer after it ("" while only the lead has come).
  final String rest;
}

OnItSplit splitOnItLead(String text) {
  final found = _lead.firstMatch(text);
  if (found == null) return OnItSplit(null, text);
  return OnItSplit(found.group(1)!.trim(), text.substring(found.end).trimLeft());
}

/// What a bot's text reply shows: the answer without its lead; the lead's
/// words alone (capitalised) when there is no answer.
String shownReply(String text) {
  final split = splitOnItLead(text);
  if (split.lead == null) return text;
  return split.rest.isNotEmpty ? split.rest : _capitalised(split.lead!);
}

/// "checking your week." → "Checking your week."; none → the default words.
String workingWords(String? activity) {
  final words = activity?.trim() ?? '';
  return _capitalised(words.isEmpty ? workingDefaultWords : words);
}

String _capitalised(String words) =>
    words.isEmpty ? words : words[0].toUpperCase() + words.substring(1);

/// "12s", "1m 05s", "1h 02m" (web WorkingIndicator formatElapsed).
String formatElapsed(Duration elapsed) {
  final total = elapsed.isNegative ? 0 : elapsed.inSeconds;
  if (total < Duration.secondsPerMinute) return '${total}s';
  final minutes = total ~/ Duration.secondsPerMinute;
  if (minutes < Duration.minutesPerHour) {
    return '${minutes}m ${_two(total % Duration.secondsPerMinute)}s';
  }
  return '${minutes ~/ Duration.minutesPerHour}h ${_two(minutes % Duration.minutesPerHour)}m';
}

String _two(int n) => n.toString().padLeft(2, '0');
