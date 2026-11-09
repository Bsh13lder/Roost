import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/call/call_words.dart';

void main() {
  test('every goodbye word is matched whole, whatever the case or punctuation', () {
    for (final w in goodbyeWords) {
      expect(isGoodbye(w), isTrue, reason: w);
      expect(isGoodbye(' ${w.toUpperCase()}! '), isTrue, reason: w);
    }
    expect(isGoodbye('Bye.'), isTrue);
    expect(isGoodbye('Hang up'), isTrue);
    expect(isGoodbye("That's all"), isTrue);
    expect(isGoodbye('¡Adiós!'), isTrue);
  });

  test('a goodbye inside a sentence is never one', () {
    expect(isGoodbye('bye the way, add milk'), isFalse);
    expect(isGoodbye('hang up the picture'), isFalse);
    expect(isGoodbye('end the call later'), isFalse);
    expect(isGoodbye('ok bye'), isFalse);
    expect(isGoodbye(''), isFalse);
    expect(isGoodbye('   '), isFalse);
  });

  test('the set is exactly the shared one', () {
    expect(goodbyeWords, {
      'bye', 'goodbye', 'bye bye', 'hang up', 'end call', 'end the call',
      "that's all", 'that is all', 'adiós', 'adios', 'hasta luego', 'cuelga', 'chao',
    });
  });
}
