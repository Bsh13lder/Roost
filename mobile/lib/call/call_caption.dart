/// The call screen's words: pure, so a test can read them without a widget.
library;

import '../features/chat/on_it_lead.dart';

/// What the bot's streamed or stored reply shows under the orb: the answer
/// without its "On it: …" lead (the lead's words alone while only the lead
/// has come). Null when there is nothing to show yet.
String? callCaption(String? text) {
  if (text == null) return null;
  final shown = shownReply(text).trim();
  return shown.isEmpty ? null : shown;
}

/// The status word while the bot works: its own live activity words
/// ("Checking your week."), or "Thinking…" before it has said any.
String thinkingWord(String? activity) {
  final words = activity?.trim() ?? '';
  return words.isEmpty ? 'Thinking…' : workingWords(words);
}
