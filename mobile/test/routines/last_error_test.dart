import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/routines/routines_repo.dart';
import 'package:roost_mobile/util/app_time.dart';

// A routine's last error in its run log (self-healing, 2026-11-10): the
// server's fixed word in plain words, with the time on the account's clock.
void main() {
  setUp(() => setAppZone('Europe/Madrid'));

  test('today shows the clock alone', () {
    final now = DateTime.utc(2026, 10, 20, 12);
    final line = lastErrorLine(
        {'last_error': {'kind': 'no_answer', 'at': '2026-10-20T10:40:00Z'}},
        now: now);
    expect(line, "Couldn't check (computer didn't answer) · 12:40");
  });

  test('an older error shows its day, every kind has words', () {
    final now = DateTime.utc(2026, 10, 20, 12);
    expect(
        lastErrorLine(
            {'last_error': {'kind': 'no_room', 'at': '2026-10-18T10:40:00Z'}},
            now: now),
        "Couldn't check (no free computer) · 18 Oct, 12:40");
    expect(lastErrorWords('run_error'), "Didn't finish");
    expect(lastErrorWords('mystery'), 'Something went wrong');
  });

  test('no error, or a malformed one, is no line', () {
    expect(lastErrorLine({'last_error': null}), isNull);
    expect(lastErrorLine({}), isNull);
    expect(lastErrorLine({'last_error': {'kind': 'no_answer'}}), isNull);
  });
}
