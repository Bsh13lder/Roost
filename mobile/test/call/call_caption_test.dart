import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/call/call_caption.dart';

void main() {
  test('the caption drops the "On it" lead once the answer streams', () {
    expect(callCaption('On it: checking your list.\nMilk is on it already.'), 'Milk is on it already.');
    expect(callCaption('On it: checking your list.'), 'Checking your list.');
    expect(callCaption('Milk is on it already.'), 'Milk is on it already.');
    expect(callCaption(null), isNull);
    expect(callCaption(''), isNull);
    expect(callCaption('   '), isNull);
  });

  test('while thinking, the status word is the bot\'s own activity words', () {
    expect(thinkingWord(null), 'Thinking…');
    expect(thinkingWord(''), 'Thinking…');
    expect(thinkingWord('checking your week.'), 'Checking your week.');
  });
}
