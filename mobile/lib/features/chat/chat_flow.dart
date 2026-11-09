import '../../api/models.dart';
import '../../chat/cards/approval_answers.dart';
import '../../chat/cards/card_base.dart';
import '../../chat/english_fix.dart';
import '../../util/app_time.dart';
import 'computer_steps.dart';
import 'on_it_lead.dart';
import 'run_steps.dart';

/// What the chat shows, in order: messages, a bot's runs (live as a pill,
/// finished as one quiet line), computer runs no run claimed, and the pill at
/// the end while the bot works with no run yet. Rendering only: every
/// message is still stored and sent to the model; technical lines just move
/// into a run's steps sheet.
class ChatFlow {
  const ChatFlow(this.items, this.texts);

  /// [Message], [ActivityItem], [ComputerRun] or [LivePillItem].
  final List<Object> items;

  /// What a bot reply shows (its answer without the "On it: …" lead, or the
  /// text streamed so far), by message id.
  final Map<String, String> texts;
}

/// A technical message folded into a run: plain words for the steps, and the
/// raw line for Technical details.
class FlowNote {
  const FlowNote({required this.kind, required this.line, required this.at, this.raw});

  /// A run_step kind ('program', 'file', 'other') or 'approved' / 'declined'.
  final String kind;
  final String line;
  final String at;
  final String? raw;
}

/// A run in the chat, with its computer card when it used the computer.
class ActivityItem {
  const ActivityItem({required this.run, this.computer, this.notes = const []});

  final ActivityRun run;
  final ComputerRun? computer;
  final List<FlowNote> notes;

  bool get live => !run.done;

  /// "Worked for 42 s · 6 steps".
  String get doneLine {
    if (run.steps.isNotEmpty) return doneWords(run, extra: notes.length);
    final n = notes.length + (computer?.count ?? 0);
    final took = notes.length < 2
        ? null
        : _time(notes.last.at).difference(_time(notes.first.at));
    final steps = n == 1 ? '1 step' : '$n steps';
    return took == null || took.inSeconds < 1
        ? 'Worked · $steps'
        : 'Worked for ${durationWords(took)} · $steps';
  }
}

/// The bot works and no run step has come yet: the working line alone.
class LivePillItem {
  const LivePillItem(this.bot, {this.words});
  final Bot bot;

  /// The streamed "On it: …" lead's words, while only the lead has come.
  final String? words;
}

/// A line that only says the bot carries on after a card: it never shows.
final _continuing = RegExp(r'^\s*Continuing\b[^\n]{0,160}$', caseSensitive: false);

/// What the reply still being written says: its lead while only the lead has
/// streamed, or that its answer has begun.
class _Writing {
  String? lead;
  bool answering = false;
}

ChatFlow buildChatFlow({
  required List<Message> messages,
  Map<String, String> answers = const {},
  List<ActivityRun> runs = const [],
  List<ComputerRun> computerRuns = const [],
  Map<String, String> streaming = const {},
  Bot? bot,
}) {
  final texts = <String, String>{};
  final writing = _Writing();
  final rows = <_Row>[];
  for (final m in messages) {
    final row = _classify(m, answers, texts, streaming, writing);
    if (row != null) rows.add(row);
  }
  final starts = {for (final r in runs) r.runId: _insertAt(rows, r.startedAt)};
  final claimed = {for (final r in runs) r.runId};
  final items = <Object>[];
  final pending = <FlowNote>[];
  String? pendingId;
  void flush() {
    if (pending.isEmpty) return;
    final id = pendingId!;
    items.add(ActivityItem(
        run: ActivityRun.empty(runId: id, botId: '', threadId: '').finished(),
        notes: List.unmodifiable(pending)));
    pending.clear();
  }

  ActivityItem? open;
  final openNotes = <FlowNote>[];
  void closeOpen() {
    if (open == null) return;
    final at = items.indexOf(open!);
    items[at] = ActivityItem(
        run: open!.run, computer: open!.computer, notes: List.unmodifiable(openNotes));
    open = null;
    openNotes.clear();
  }

  void placeRunsAt(int index) {
    for (final r in runs.where((r) => starts[r.runId] == index)) {
      flush();
      closeOpen();
      final item = ActivityItem(run: r, computer: _computerFor(r, computerRuns));
      items.add(item);
      open = item;
    }
    for (final c in computerRuns.where(
        (c) => !claimed.contains(c.runId) && _insertAt(rows, c.startedAt) == index)) {
      flush();
      items.add(c);
    }
  }

  for (var i = 0; i < rows.length; i++) {
    placeRunsAt(i);
    final row = rows[i];
    if (row.note != null) {
      if (open != null) {
        openNotes.add(row.note!);
      } else {
        if (pending.isEmpty) pendingId = row.message.id;
        pending.add(row.note!);
      }
      continue;
    }
    flush();
    if (row.message.fromUser && row.message.kind == 'text') closeOpen();
    items.add(row.message);
  }
  placeRunsAt(rows.length);
  flush();
  closeOpen();
  final busy = bot != null && (bot.status == BotStatus.onIt || writing.lead != null);
  final running = items.any((i) => i is ActivityItem && i.live);
  // One robot per working message: once its answer streams, the bubble alone.
  if (busy && !running && !writing.answering) {
    items.add(LivePillItem(bot, words: writing.lead));
  }
  return ChatFlow(List.unmodifiable(_underTheirMessages(items)), Map.unmodifiable(texts));
}

/// An english_fix line moves right under the message it names; one whose
/// message is not loaded (or whose body cannot be read) keeps its place.
List<Object> _underTheirMessages(List<Object> items) {
  final out = List<Object>.of(items);
  for (final item in items) {
    if (item is! Message || item.kind != 'english_fix') continue;
    final forId = parseEnglishFix(item.body)?.messageId;
    final target = forId == null || forId.isEmpty
        ? -1
        : out.indexWhere((o) => o is Message && o.id == forId && o.id != item.id);
    if (target == -1) continue;
    out.remove(item);
    out.insert(out.indexWhere((o) => o is Message && o.id == forId) + 1, item);
  }
  return out;
}

/// One message: shown as it is, folded into a run as a note, or dropped.
class _Row {
  const _Row(this.message, [this.note]);
  final Message message;
  final FlowNote? note;
}

_Row? _classify(Message m, Map<String, String> answers, Map<String, String> texts,
    Map<String, String> streaming, _Writing writing) {
  switch (m.kind) {
    case 'card_answer':
    case 'approval_result':
      return null; // the card itself says yes or no
    case 'program_activity':
      return _Row(m, _programNote(m));
    case 'task_cards':
      return _Row(m); // the tasks a run added or listed: a card of its own
    case 'english_fix':
      return _Row(m); // the corrected copy of your words: a card under them
    case 'routine_note':
    case 'question_note':
      return _Row(m); // a routine's or the question book's own quiet line, never a step of a run
    case 'approval':
      final ref = parseApprovalMessage(m.body);
      final answer = ref == null ? null : answers[ref.cardId];
      if (answer == null) return _Row(m); // still waiting for you
      final yes = !answer.trimLeft().toLowerCase().startsWith('no');
      return _Row(
          m,
          FlowNote(
              kind: yes ? 'approved' : 'declined',
              line: yes ? 'You said yes' : 'You said no',
              at: m.createdAt,
              raw: answer));
  }
  if (m.role == 'activity') {
    return _Row(m, FlowNote(kind: 'other', line: m.body.trim(), at: m.createdAt));
  }
  if (m.role == 'bot' && m.kind == 'text') return _botText(m, texts, streaming, writing);
  return _Row(m);
}

/// A bot's text reply: its answer without the "On it: …" lead. While it is
/// still being written and only the lead has come, the lead is the working
/// line's words instead of a bubble.
_Row? _botText(Message m, Map<String, String> texts, Map<String, String> streaming, _Writing writing) {
  final raw = _withoutContinuing(streaming[m.id] ?? m.body);
  if (raw == null) return null;
  if (!m.isPlaceholder) {
    texts[m.id] = shownReply(raw);
    return _Row(m);
  }
  final split = splitOnItLead(raw);
  if (split.lead != null && split.rest.isEmpty) {
    writing.lead = split.lead;
    return null;
  }
  if (raw.trim().isEmpty) return null;
  writing.answering = true;
  texts[m.id] = split.rest;
  return _Row(m);
}

/// The reply without a "Continuing: …" first line; null when that is all it says.
String? _withoutContinuing(String text) {
  final body = text.trimLeft();
  final cut = body.indexOf('\n');
  final first = cut == -1 ? body : body.substring(0, cut);
  if (!_continuing.hasMatch(first)) return text;
  final rest = cut == -1 ? '' : body.substring(cut + 1).trim();
  return rest.isEmpty ? null : rest;
}

FlowNote _programNote(Message m) {
  final d = decodeBody(m.body);
  final op = d?['op'];
  if (op == 'write') {
    return FlowNote(
        kind: 'file', line: 'Saved a file', at: m.createdAt, raw: 'Wrote ${str(d?['path'])}');
  }
  final code = (d?['exit_code'] as num?)?.toInt() ?? 0;
  final timedOut = d?['timed_out'] == true;
  final ok = !timedOut && code == 0;
  final command = str(d?['command']).replaceAll('\n', ' ');
  return FlowNote(
    kind: 'program',
    line: ok ? 'Ran a program' : (timedOut ? 'A program took too long' : 'A program failed'),
    at: m.createdAt,
    raw: command.isEmpty ? null : 'Ran: $command · ${timedOut ? 'timed out' : 'exit $code'}',
  );
}

/// Right after your last message at or before [iso] (0: before everything).
int _insertAt(List<_Row> rows, String iso) {
  final start = _time(iso);
  var at = 0;
  for (var i = 0; i < rows.length; i++) {
    final m = rows[i].message;
    if (m.fromUser && m.kind == 'text' && !_time(m.createdAt).isAfter(start)) at = i + 1;
  }
  return at;
}

ComputerRun? _computerFor(ActivityRun run, List<ComputerRun> computerRuns) {
  for (final c in computerRuns) {
    if (c.runId == run.runId) return c;
  }
  return null;
}

DateTime _time(String iso) {
  try {
    return parseServerTime(iso);
  } on FormatException {
    return DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
  }
}
