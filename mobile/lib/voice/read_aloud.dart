import '../api/models.dart';

/// Kinds a bot can be heard saying: a text reply and a Report.
const spokenKinds = {'text', 'report'};

/// Whether [m] has a speaker: a finished bot reply or Report.
bool canSpeak(Message m) =>
    m.role == 'bot' && m.seq > 0 && spokenKinds.contains(m.kind);

/// Read replies aloud: the newest bot reply that arrived between two states of
/// the open chat, or null. A message already there (a reload, a resumed
/// socket replaying it) never counts; a streamed reply counts once it is
/// finished. [alreadyRead] keeps a reply from playing twice.
String? newReplyToRead({
  required List<Message> before,
  required List<Message> after,
  required Set<String> alreadyRead,
}) {
  final finished = {
    for (final m in before)
      if (m.seq > 0) m.id,
  };
  String? newest;
  for (final m in after) {
    if (canSpeak(m) &&
        !finished.contains(m.id) &&
        !alreadyRead.contains(m.id)) {
      newest = m.id;
    }
  }
  return newest;
}

/// Plays only in the chat that is open, on top and in the foreground, for a
/// bot whose voice says Read replies aloud.
bool shouldReadAloud({
  required bool readAloud,
  required bool foreground,
  required bool onTop,
  required bool loaded,
}) => readAloud && foreground && onTop && loaded;
