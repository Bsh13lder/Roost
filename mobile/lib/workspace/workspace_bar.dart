import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../board/common/widgets.dart';
import '../board/tasks/paste_list.dart';
import '../board/tasks/quick_add.dart';
import '../board/tasks/quick_chips.dart';
import '../board/tasks/quick_draft.dart';
import '../board/tasks/quick_kept.dart';
import '../board/tasks/quick_suggest.dart';
import '../board/tasks/task_dates.dart';
import '../board/tasks/task_models.dart';
import '../board/tasks/task_repo.dart';
import '../live/live_connection.dart';
import '../theme/tokens.dart';
import 'bar/bar_pill.dart';
import 'bar/bar_picks.dart';
import 'bar/paste_catch.dart';
import 'bar/paste_sheet.dart';
import 'bar/quick_sources.dart';
import 'bar/reading_chips.dart';
import 'bar/section_switch.dart';
import 'bar/suggest_strip.dart';
import 'workspace_state.dart';

/// The fixed bottom bar: "Add or find anything…" (typing filters the view;
/// Enter or + adds the line as a task, read by the server) and the
/// Tasks · Notes · Calendar switch. While you type it suggests /Project,
/// #tag, @bot and !priority, offers picker buttons, and shows the server's
/// reading as chips with ×. On the Calendar a line naming no day is due on
/// the chosen day.
class WorkspaceBar extends ConsumerStatefulWidget {
  const WorkspaceBar({super.key});

  @override
  ConsumerState<WorkspaceBar> createState() => _WorkspaceBarState();
}

class _WorkspaceBarState extends ConsumerState<WorkspaceBar> with BarPicks {
  @override
  final text = TextEditingController();
  final _focus = FocusNode();
  Timer? _timer;
  int _ticket = 0;
  @override
  QuickReading? reading;
  @override
  QuickDraft draft = const QuickDraft(text: '');
  String? _error;
  bool _busy = false;
  bool _wantsTags = false;
  bool _wantsBots = false;
  @override
  bool wantsProjects = false;

  @override
  void initState() {
    super.initState();
    text.addListener(_redraw);
    _focus.addListener(_redraw);
  }

  void _redraw() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _timer?.cancel();
    text.dispose();
    _focus.dispose();
    super.dispose();
  }

  /// The draft with the day a line naming none gets (a calendar day).
  QuickDraft get _full {
    final day = ref.read(quickDefaultDayProvider);
    return draft.withDefaultDue(day == null ? null : isoDay(day));
  }

  void _changed(String value) {
    ref.read(workspaceQueryProvider.notifier).state = value;
    setState(() {
      draft = draft.withText(value);
      _error = null;
      wantsProjects |= value.contains('/');
      _wantsTags |= value.contains('#');
      _wantsBots |= value.contains('@');
    });
    reread();
  }

  /// Asks the server again after a pause; only the newest answer counts.
  @override
  void reread() {
    _timer?.cancel();
    final ticket = ++_ticket;
    if (text.text.trim().isEmpty) {
      setState(() => reading = null);
      return;
    }
    _timer = Timer(quickParseDelay, () => _read(ticket));
  }

  Future<void> _read(int ticket) async {
    try {
      final r = await ref.read(taskRepoProvider).parseDraft(_full);
      if (mounted && ticket == _ticket) setState(() => reading = r);
    } on ApiException {
      // The chips are a preview only; Add says what went wrong.
    }
  }

  @override
  void setLine(String value, [int? caret]) {
    text.value = TextEditingValue(
      text: value,
      selection: TextSelection.collapsed(offset: caret ?? value.length),
    );
    _changed(value);
    _focus.requestFocus();
  }

  void _clear() {
    text.clear();
    ref.read(workspaceQueryProvider.notifier).state = '';
    setState(() {
      draft = const QuickDraft(text: '');
      reading = null;
      _error = null;
    });
  }

  Future<void> _add() async {
    if (text.text.trim().isEmpty || _busy) return;
    _timer?.cancel();
    ++_ticket;
    setState(() => _busy = true);
    try {
      final added = await addQuickLine(ref.read(taskRepoProvider), _full);
      ref.invalidate(taskListProvider);
      ref.invalidate(taskCountsProvider);
      if (!mounted) return;
      _clear();
      snack(context, 'Added: ${added.title}');
    } on QuickAddProblem catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Paste: a list of two or more lines (on Tasks or the Calendar) offers
  /// "Add N tasks?"; anything else is typed into the line.
  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final pasted = data?.text;
    if (pasted == null || pasted.isEmpty || !mounted) return;
    if (_hasPickersNow && isPastedList(pasted)) {
      _focus.unfocus();
      final added = await showPasteSheet(context, pasted);
      if (added == 0 || !mounted) return;
      ref.invalidate(taskListProvider);
      ref.invalidate(taskCountsProvider);
      snack(context, added == 1 ? 'Added 1 task' : 'Added $added tasks');
      return;
    }
    final next = pasteInto(text.value, pasted, maxQuickLine);
    setLine(next.text, next.selection.baseOffset);
  }

  void _remove(QuickChip chip) {
    setState(() {
      draft = chip.kind == 'picked-reminder'
          ? draft.withRemind(null)
          : chip.words.isNotEmpty
              ? draft.keeping(chip.words)
              : draft.skipping(chip.kind);
    });
    reread();
  }

  void _confirmBot(String id) => setState(() => draft = draft.withBot(id));

  SuggestSources _sources() => SuggestSources(
        projects: wantsProjects
            ? [for (final p in ref.watch(taskProjectsProvider).valueOrNull ?? const <ProjectRef>[]) p.name]
            : const [],
        tags: _wantsTags ? ref.watch(quickTagsProvider).valueOrNull ?? const [] : const [],
        bots: _wantsBots ? [for (final b in ref.watch(liveProvider).bots.values) b.name] : const [],
      );

  Suggestion? _suggestion() {
    final sel = text.selection;
    if (!_focus.hasFocus || text.text.isEmpty) return null;
    final caret = sel.isValid && sel.isCollapsed ? sel.baseOffset : text.text.length;
    return suggest(text.text, caret, _sources());
  }

  void _pickSuggestion(Suggestion s, SuggestOption o) {
    final r = acceptSuggestion(text.text, s, o);
    setLine(r.text, r.caret);
  }

  List<QuickChip> _chips(DateTime? day) {
    final chips = chipsOf(
      reading ?? const QuickReading({}),
      dayBadge: day == null ? null : dayBadge(day),
      remindLabel: remindLabel,
      confirmedBot: draft.confirmedBot,
    );
    return [for (final c in chips) if (!isCancelled(c.words, draft.keep)) c];
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(quickDefaultDayProvider, (_, _) => reread());
    final day = ref.watch(quickDefaultDayProvider);
    final typed = text.text.trim().isNotEmpty;
    final suggestion = _suggestion();
    return Material(
      color: Tokens.bg,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
              Tokens.space3, Tokens.space2, Tokens.space3, Tokens.space3),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (suggestion != null)
                _gap(SuggestStrip(
                  options: suggestion.options,
                  onPick: (o) => _pickSuggestion(suggestion, o),
                )),
              if (typed) _gap(_reading(day)),
              if (_hint != null) _gap(_hintText(_hint!, _error != null)),
              if ((typed || _focus.hasFocus) && _hasPickers) _gap(pickerRow(day)),
              Row(children: [
                Expanded(
                  child: BarPill(
                    controller: text,
                    focusNode: _focus,
                    busy: _busy,
                    onChanged: _changed,
                    onAdd: _add,
                    onPaste: _paste,
                  ),
                ),
                const SizedBox(width: Tokens.space2),
                const SectionSwitch(),
              ]),
            ],
          ),
        ),
      ),
    );
  }

  /// The picker buttons set a task's details, so they show on Tasks and
  /// the Calendar only, never on Notes.
  bool get _hasPickers =>
      ref.watch(workspaceSectionProvider) != WorkspaceSection.notes;

  /// The same, read outside build (a paste).
  bool get _hasPickersNow =>
      ref.read(workspaceSectionProvider) != WorkspaceSection.notes;

  Widget _reading(DateTime? day) {
    final r = reading;
    final title = r != null && r.title != text.text.trim() ? r.title : null;
    return ReadingChips(
      chips: _chips(day),
      title: title,
      onRemove: _remove,
      onConfirmBot: _confirmBot,
    );
  }

  /// What went wrong on Add, or what the server waits for before it can.
  String? get _hint {
    if (_error != null) return _error;
    final b = reading?.blockerFor(draft.confirmedBot);
    return b == 'Give the task a title.' ? null : b;
  }

  Widget _hintText(String words, bool error) => Text(words,
      key: Key(error ? 'quick-error' : 'quick-hint'),
      style: TextStyle(
          color: error ? Tokens.dangerText : Tokens.textSecondary,
          fontSize: Tokens.fsLabel));

  Widget _gap(Widget child) => Padding(
      padding: const EdgeInsets.only(bottom: Tokens.space2), child: child);
}
