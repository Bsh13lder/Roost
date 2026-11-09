import 'quick_kept.dart';
import 'task_models.dart';

/// Everything a quick line sends besides its text: kinds dismissed with no
/// words to keep (`skip`), words whose chips were cancelled (`keep`), the day
/// a line that names none gets (`default_due`, a calendar day), a Remind me
/// pick, and the bot you confirmed handing the task to. Immutable.
class QuickDraft {
  const QuickDraft({
    required this.text,
    this.skip = const [],
    this.keep = const [],
    this.defaultDue,
    this.remindWire,
    this.confirmedBot,
  });

  final String text;
  final List<String> skip;
  final List<String> keep;

  /// "YYYY-MM-DD": used by the server only when the line names no day.
  final String? defaultDue;

  /// A wall time on the account's clock from Remind me ("2026-10-23T08:00").
  final String? remindWire;
  final String? confirmedBot;

  static const _unset = Object();

  QuickDraft _copy({
    String? text,
    List<String>? skip,
    List<String>? keep,
    Object? defaultDue = _unset,
    Object? remindWire = _unset,
    Object? confirmedBot = _unset,
  }) =>
      QuickDraft(
        text: text ?? this.text,
        skip: skip ?? this.skip,
        keep: keep ?? this.keep,
        defaultDue: identical(defaultDue, _unset) ? this.defaultDue : defaultDue as String?,
        remindWire: identical(remindWire, _unset) ? this.remindWire : remindWire as String?,
        confirmedBot:
            identical(confirmedBot, _unset) ? this.confirmedBot : confirmedBot as String?,
      );

  /// New text: kept words no longer typed are let go; an empty line starts
  /// over (the default day stays).
  QuickDraft withText(String value) => value.trim().isEmpty
      ? QuickDraft(text: value, defaultDue: defaultDue)
      : _copy(text: value, keep: stillTyped(keep, value));

  QuickDraft keeping(List<String> words) => _copy(keep: keepWords(keep, words));

  QuickDraft skipping(String kind) =>
      skip.contains(kind) ? this : _copy(skip: [...skip, kind]);

  QuickDraft withDefaultDue(String? day) => _copy(defaultDue: day);

  QuickDraft withRemind(String? wire) => _copy(remindWire: wire);

  QuickDraft withBot(String? id) => _copy(confirmedBot: id);

  /// The body for `POST /api/tasks/parse`.
  Map<String, dynamic> parseBody() => {
        'text': text,
        if (skip.isNotEmpty) 'skip': skip,
        if (keep.isNotEmpty) 'keep': keep,
        'default_due': ?defaultDue,
      };

  /// The body for `POST /api/tasks`: the server's reading, plus a Remind me
  /// pick (that time alone, no advance reminder, as the drawer does).
  Map<String, dynamic> createBody(QuickReading reading) => {
        ...reading.toTaskIn(confirmedBot),
        if (remindWire != null) ...{
          'reminder_at': remindWire,
          'pre_reminders': <String>[],
        },
      };
}
