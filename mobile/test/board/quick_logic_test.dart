import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/quick_chips.dart';
import 'package:roost_mobile/board/tasks/quick_draft.dart';
import 'package:roost_mobile/board/tasks/quick_insert.dart';
import 'package:roost_mobile/board/tasks/quick_kept.dart';
import 'package:roost_mobile/board/tasks/quick_suggest.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';

const sources = SuggestSources(
  projects: ['Club', 'Casa Nueva'],
  tags: ['shopping', 'home'],
  bots: ['Scout'],
);

void main() {
  group('suggest', () {
    test('finds the token at the caret and its names', () {
      final s = suggest('Pay /C', 6, sources)!;
      expect(s.trigger, '/');
      expect(s.start, 4);
      expect(s.options.map((o) => o.insert), ['/Club', '/Casa Nueva']);
    });

    test('a token must start a word', () {
      expect(suggest('mail@Sc', 7, sources), isNull);
    });

    test('levels match their key and aliases', () {
      final s = suggest('x !h', 4, sources)!;
      expect(s.options.single.insert, '!high');
      expect(suggest('x !!!', 5, sources), isNull);
    });

    test('tags are one word; a whole name has nothing left to finish', () {
      expect(suggest('#shop ping', 10, sources), isNull);
      expect(suggest('x #shopping', 11, sources), isNull);
      expect(suggest('x @s', 4, sources)!.options.single.insert, '@Scout');
    });

    test('accept replaces the token and adds one space', () {
      final s = suggest('Pay /C rent', 6, sources)!;
      final r = acceptSuggestion('Pay /C rent', s, s.options.first);
      expect(r.text, 'Pay /Club rent');
      expect(r.caret, 10);
      final end = suggest('Pay /C', 6, sources)!;
      expect(acceptSuggestion('Pay /C', end, end.options.first).text, 'Pay /Club ');
    });
  });

  group('insert', () {
    test('a pick replaces the earlier words of its chip', () {
      expect(insertWords('Pay rent !low', '!urgent', const ['!low']), 'Pay rent !urgent');
      expect(insertWords('Pay rent', '/Club'), 'Pay rent /Club');
      expect(insertWords('Pay rent friday', '', const ['friday']), 'Pay rent');
    });

    test('day words read like the web picker', () {
      expect(dayWords(DateTime.utc(2026, 10, 21)), '2026-10-21');
      expect(dayWords(DateTime.utc(2026, 10, 21), '09:00'), '2026-10-21 at 09:00');
    });

    test('tag words and name filtering', () {
      expect(tagWords(' #big shop '), '#big-shop');
      expect(tagWords('1x'), isNull);
      expect(filterNames(const ['Home', 'Club house', 'Casa'], 'h'), ['Home', 'Club house']);
    });
  });

  group('kept', () {
    test('keeps words once and lets go of words no longer typed', () {
      expect(keepWords(const ['!high'], const ['!HIGH', 'friday']), ['!high', 'friday']);
      expect(stillTyped(const ['friday', '!high'], 'Call Ana friday'), ['friday']);
      expect(isCancelled(const ['friday'], const ['Friday']), isTrue);
      expect(isCancelled(const [], const ['friday']), isFalse);
    });
  });

  group('draft', () {
    test('the parse body carries skip, keep and the default due', () {
      const d = QuickDraft(text: 'Call', skip: ['star'], keep: ['friday'], defaultDue: '2026-10-21');
      expect(d.parseBody(), {
        'text': 'Call',
        'skip': ['star'],
        'keep': ['friday'],
        'default_due': '2026-10-21',
      });
      expect(const QuickDraft(text: 'Call').parseBody(), {'text': 'Call'});
    });

    test('a picked reminder rides in the create body with no advance one', () {
      const r = QuickReading({'title': 'Call', 'ready': true, 'due_date': '2026-10-21'});
      const d = QuickDraft(text: 'Call', remindWire: '2026-10-21T08:00');
      expect(d.createBody(r), {
        'title': 'Call',
        'due_date': '2026-10-21',
        'reminder_at': '2026-10-21T08:00',
        'pre_reminders': <String>[],
      });
    });

    test('a bot is handed the task only once confirmed', () {
      const r = QuickReading({
        'title': 'Book', 'ready': true, 'assignee': {'id': 'b1', 'name': 'Scout'},
      });
      expect(r.blockerFor(null), 'Confirm handing this to Scout first.');
      expect(r.blockerFor('b1'), isNull);
      const d = QuickDraft(text: 'Book @Scout', confirmedBot: 'b1');
      expect(d.createBody(r), {'title': 'Book', 'assign_bot_id': 'b1', 'assign_confirmed': true});
    });
  });

  group('chips', () {
    test('chips carry the words they came from', () {
      const r = QuickReading({
        'title': 'Pay', 'ready': true, 'priority': 'high', 'starred': true, 'tags': ['home'],
        'due_date': '2026-10-23', 'due_text': 'Fri 23 Oct',
        'matches': {'priority': ['!high'], 'date': ['friday']},
      });
      final chips = chipsOf(r);
      expect(chips.map((c) => c.label), ['Due Fri 23 Oct', '!high', '#home', 'Starred']);
      expect(chips.first.words, ['friday']);
      expect(chips.last.words, isEmpty);
    });

    test('a default day shows as a fixed badge while the line names no day', () {
      const r = QuickReading({
        'title': 'Pay', 'ready': true, 'due_date': '2026-10-21', 'due_text': 'Wed 21 Oct',
      });
      final chips = chipsOf(r, dayBadge: 'Due Wed 21 Oct');
      expect(chips.single.label, 'Due Wed 21 Oct');
      expect(chips.single.removable, isFalse);
    });

    test('a budget in no project counts in General and is added', () {
      const r = QuickReading({
        'title': 'Buy shoes', 'ready': true, 'budget': '30.00', 'budget_words': '€30',
        'budget_currency': 'EUR',
      });
      expect(chipsOf(r).single.label, 'Budget 30.00');
      expect(chipsOf(r).single.tone, ChipTone.read);
      expect(r.toTaskIn(), {'title': 'Buy shoes', 'allocated_budget': '30.00'});
      expect(r.blockerFor(null), isNull);
      const foreign = QuickReading({
        'title': 'Buy shoes', 'ready': false, 'budget_words': r'$30',
        'budget_problem': '“General” keeps its money in EUR: write the budget in EUR.',
      });
      expect(chipsOf(foreign).single.tone, ChipTone.ask);
      expect(foreign.blockerFor(null),
          '“General” keeps its money in EUR: write the budget in EUR.');
      expect(foreign.toTaskIn(), {'title': 'Buy shoes'});
    });

    test('a picked reminder replaces the line reminder chip', () {
      const r = QuickReading({'title': 'Pay', 'ready': true, 'reminder_text': 'Thu', 'reminder_at': 'x'});
      final chips = chipsOf(r, remindLabel: 'Remind Fri 23 Oct, 08:00');
      expect(chips.single.label, 'Remind Fri 23 Oct, 08:00');
      expect(chips.single.kind, 'picked-reminder');
    });
  });
}
