import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/task_dates.dart';
import 'package:roost_mobile/util/app_time.dart';

void main() {
  tearDown(() => setAppZone('Europe/Madrid'));

  test('a known IANA zone becomes the app zone', () {
    expect(setAppZone('America/New_York'), isTrue);
    expect(appZoneName(), 'America/New_York');
    expect(appLocation().name, 'America/New_York');
  });

  test('null or an unknown zone changes nothing', () {
    setAppZone('Asia/Tokyo');
    expect(setAppZone(null), isFalse);
    expect(setAppZone('Mars/Olympus'), isFalse);
    expect(appZoneName(), 'Asia/Tokyo');
  });

  test("the zone's city comes from its IANA name", () {
    expect(zoneCity('Europe/Madrid'), 'Madrid');
    expect(zoneCity('America/New_York'), 'New York');
    expect(zoneCity('America/Argentina/Buenos_Aires'), 'Buenos Aires');
    expect(zoneCity('UTC'), 'UTC');
  });

  test('clocks follow the app zone and carry no city', () {
    const iso = '2026-10-23T12:19:00Z';
    expect(appClock(iso), '14:19');
    expect(appDayClock(iso), 'Fri 23 Oct, 14:19');
    setAppZone('America/New_York');
    expect(appClock(iso), '08:19');
    expect(appDayClock(iso), 'Fri 23 Oct, 08:19');
  });

  test('a non-Madrid zone shifts a due time label and its day', () {
    const due = '2026-10-23T22:30:00+00:00';
    final madridToday = DateTime.utc(2026, 10, 24);
    expect(dueWords(due, today: madridToday), 'Today 00:30');
    setAppZone('America/Los_Angeles');
    expect(dueWords(due, today: DateTime.utc(2026, 10, 23)), 'Today 15:30');
  });

  test("the account's day and minute of the day", () {
    final at = DateTime.utc(2026, 10, 22, 23, 30);
    expect(appDay(at), DateTime.utc(2026, 10, 23));
    expect(appMinuteOfDay(at), 90);
    setAppZone('UTC');
    expect(appDay(at), DateTime.utc(2026, 10, 22));
    expect(appMinuteOfDay(at), 23 * 60 + 30);
  });
}
