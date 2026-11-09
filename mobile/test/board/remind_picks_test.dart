import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/remind_picks.dart';

void main() {
  test('a timed due offers four picks, counted back on Madrid time', () {
    final picks = remindPicks('2026-12-01T09:00:00+01:00');
    expect([for (final p in picks) p.label],
        ['At the due time', '10 min before', '1 hour before', '1 day before']);
    expect([for (final p in picks) p.wire],
        ['2026-12-01T09:00', '2026-12-01T08:50', '2026-12-01T08:00', '2026-11-30T09:00']);
  });

  test('the picks follow summer time in Madrid', () {
    // 09:00 Madrid on 1 Jul is 07:00 UTC.
    expect(remindPicks('2026-07-01T07:00:00+00:00').first.wire, '2026-07-01T09:00');
  });

  test('a day with no time, or no due, offers no picks (pick a time instead)', () {
    expect(remindPicks('2026-12-01'), isEmpty);
    expect(remindPicks(null), isEmpty);
    expect(remindPicks('soon'), isEmpty);
  });

  test('the row says when, or Off', () {
    expect(reminderWords(null), 'Off');
    expect(reminderWords('2026-12-01T07:50:00+00:00'), 'Tue 1 Dec, 08:50');
  });

  test('a pick reads as its Madrid day and clock', () {
    expect(wireWords('2026-12-01T08:50'), 'Tue 1 Dec, 08:50');
  });

  test('a chosen day and time is sent as Madrid wall time', () {
    expect(appWire(DateTime.utc(2026, 12, 1, 7, 50)), '2026-12-01T08:50');
  });
}
