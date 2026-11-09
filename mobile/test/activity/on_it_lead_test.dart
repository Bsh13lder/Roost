import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/features/chat/on_it_lead.dart';

void main() {
  test('a reply opening with On it splits into its lead and the answer', () {
    final s = splitOnItLead('On it: checking your week.\n\nYou have two meetings.');
    expect(s.lead, 'checking your week.');
    expect(s.rest, 'You have two meetings.');
  });

  test('the lead is found with a comma, a dash, any case and leading space', () {
    expect(splitOnItLead('  on it, looking').lead, 'looking');
    expect(splitOnItLead('ON IT — reading the page').lead, 'reading the page');
    expect(splitOnItLead('On it - here').lead, 'here');
  });

  test('a reply with no lead is left whole', () {
    final s = splitOnItLead('Done, here it is.');
    expect(s.lead, isNull);
    expect(s.rest, 'Done, here it is.');
    expect(splitOnItLead('I am on it: later').lead, isNull);
  });

  test('only the lead streamed so far: no answer yet', () {
    final s = splitOnItLead('On it: checking your week.');
    expect(s.lead, 'checking your week.');
    expect(s.rest, '');
  });

  test('the shown reply is the answer, or the lead alone when there is no answer', () {
    expect(shownReply('On it: x\n\nAnswer.'), 'Answer.');
    expect(shownReply('On it: added milk to your list.'), 'Added milk to your list.');
    expect(shownReply('Plain answer.'), 'Plain answer.');
  });

  test('working words: capitalised, the default when there are none', () {
    expect(workingWords('checking your week.'), 'Checking your week.');
    expect(workingWords(null), 'Reading your message');
    expect(workingWords('   '), 'Reading your message');
  });

  test('elapsed time reads as the web does', () {
    expect(formatElapsed(const Duration(seconds: 12)), '12s');
    expect(formatElapsed(const Duration(minutes: 1, seconds: 5)), '1m 05s');
    expect(formatElapsed(const Duration(hours: 1, minutes: 2)), '1h 02m');
    expect(formatElapsed(const Duration(seconds: -3)), '0s');
  });
}
