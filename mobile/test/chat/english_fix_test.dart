import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/chat/english_fix.dart';

String body(Map<String, Object?> j) => jsonEncode(j);

void main() {
  group('parseEnglishFix', () {
    test('reads the sealed body the server posts', () {
      final fix = parseEnglishFix(body({
        'message_id': 'u1',
        'said': 'I has two cat',
        'corrected': 'I have two cats',
        'fixes': [
          {'wrong': 'has', 'right': 'have'},
          {'wrong': 'cat', 'right': 'cats'},
        ],
      }));
      expect(fix, isNotNull);
      expect(fix!.messageId, 'u1');
      expect(fix.said, 'I has two cat');
      expect(fix.corrected, 'I have two cats');
      expect(fix.fixes, const [
        WordFix('has', 'have'),
        WordFix('cat', 'cats'),
      ]);
    });

    test('anything unreadable is null; broken fixes are skipped', () {
      expect(parseEnglishFix('not json'), isNull);
      expect(parseEnglishFix('[]'), isNull);
      expect(parseEnglishFix(body({'said': 'x'})), isNull,
          reason: 'no corrected sentence');
      expect(parseEnglishFix(body({'corrected': 'x'})), isNull,
          reason: 'no said sentence');
      final fix = parseEnglishFix(body({
        'message_id': 7,
        'said': 'a',
        'corrected': 'b',
        'fixes': [
          {'wrong': 'a', 'right': 'b'},
          {'wrong': 1, 'right': 'b'},
          'junk',
          {'wrong': 'a'},
        ],
      }));
      expect(fix!.messageId, '');
      expect(fix.fixes, const [WordFix('a', 'b')]);
      expect(parseEnglishFix(body({'said': 'a', 'corrected': 'b', 'fixes': 'no'}))!.fixes,
          isEmpty);
    });
  });

  group('fixSegments', () {
    test('the corrected sentence with each fix inline: wrong struck, right after it', () {
      const fix = EnglishFix(
        messageId: 'u1',
        said: 'I has two cat',
        corrected: 'I have two cats',
        fixes: [WordFix('has', 'have'), WordFix('cat', 'cats')],
      );
      final shown = fixSegments(fix);
      expect(shown.segments.map((s) => (s.kind, s.text)).toList(), [
        (FixPart.plain, 'I '),
        (FixPart.wrong, 'has'),
        (FixPart.right, 'have'),
        (FixPart.plain, ' two '),
        (FixPart.wrong, 'cat'),
        (FixPart.right, 'cats'),
      ]);
      expect(shown.unplaced, isEmpty);
    });

    test('no fixes: the sentence alone', () {
      const fix = EnglishFix(messageId: '', said: 'Fine.', corrected: 'Fine.', fixes: []);
      final shown = fixSegments(fix);
      expect(shown.segments.map((s) => (s.kind, s.text)).toList(), [(FixPart.plain, 'Fine.')]);
      expect(shown.unplaced, isEmpty);
    });

    test('a fix whose wrong words are not in what you said goes to the end as wrong → right', () {
      const fix = EnglishFix(
        messageId: '',
        said: 'She go home',
        corrected: 'She goes home',
        fixes: [WordFix('went', 'goes'), WordFix('go', 'goes')],
      );
      final shown = fixSegments(fix);
      expect(shown.segments.map((s) => (s.kind, s.text)).toList(), [
        (FixPart.plain, 'She '),
        (FixPart.wrong, 'go'),
        (FixPart.right, 'goes'),
        (FixPart.plain, ' home'),
      ]);
      expect(shown.unplaced, const [WordFix('went', 'goes')]);
    });

    test('a fix whose right words are not in the corrected sentence also goes to the end', () {
      const fix = EnglishFix(
        messageId: '',
        said: 'I has it',
        corrected: 'I have it',
        fixes: [WordFix('has', 'had')],
      );
      final shown = fixSegments(fix);
      expect(shown.segments.map((s) => (s.kind, s.text)).toList(), [(FixPart.plain, 'I have it')]);
      expect(shown.unplaced, const [WordFix('has', 'had')]);
    });

    test('a right word that repeats is placed in order, not twice at the first one', () {
      const fix = EnglishFix(
        messageId: '',
        said: 'the cat and the dog',
        corrected: 'the cat and the dog',
        fixes: [WordFix('teh', 'the'), WordFix('teh', 'the')],
      );
      final shown = fixSegments(fix);
      expect(shown.unplaced, hasLength(2), reason: '"teh" is not in what you said');
      expect(shown.segments.map((s) => s.text).join(), 'the cat and the dog');
    });

    test('an empty right (a word to drop) is never placed inline', () {
      const fix = EnglishFix(
        messageId: '',
        said: 'I am agree',
        corrected: 'I agree',
        fixes: [WordFix('am', '')],
      );
      final shown = fixSegments(fix);
      expect(shown.segments.map((s) => s.text).join(), 'I agree');
      expect(shown.unplaced, const [WordFix('am', '')]);
    });

    test('words are found case-insensitively in the corrected sentence', () {
      const fix = EnglishFix(
        messageId: '',
        said: 'tomorrow i go',
        corrected: 'Tomorrow I go',
        fixes: [WordFix('i', 'I')],
      );
      final shown = fixSegments(fix);
      expect(shown.segments.map((s) => (s.kind, s.text)).toList(), [
        (FixPart.plain, 'Tomorrow '),
        (FixPart.wrong, 'i'),
        (FixPart.right, 'I'),
        (FixPart.plain, ' go'),
      ]);
    });
  });

  test('arrowLine spells an unplaced fix', () {
    expect(arrowLine(const WordFix('went', 'goes')), 'went → goes');
    expect(arrowLine(const WordFix('am', '')), 'am → (drop it)');
  });
}
