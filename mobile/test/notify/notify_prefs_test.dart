import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/notify/notify_prefs.dart';

void main() {
  test('off by default, every kind on, quiet hours off at 23:00–07:00', () {
    const p = NotifyPrefs();
    expect(p.stayConnected, isFalse);
    expect([p.needsOk, p.reports, p.replies, p.reminders], everyElement(isTrue));
    expect(p.quietOn, isFalse);
    expect(p.quietFrom, 23 * 60);
    expect(p.quietTo, 7 * 60);
  });

  test('round-trips through JSON and copyWith leaves the original alone', () {
    const p = NotifyPrefs(stayConnected: true, replies: false, quietOn: true, quietFrom: 60, quietTo: 120);
    expect(NotifyPrefs.fromJson(p.toJson()), p);
    final q = p.copyWith(replies: true);
    expect(p.replies, isFalse);
    expect(q.replies, isTrue);
  });

  test('bad stored data falls back to the defaults', () {
    expect(NotifyPrefs.fromJson(null), const NotifyPrefs());
    expect(NotifyPrefs.fromJson('nonsense'), const NotifyPrefs());
    expect(NotifyPrefs.fromJson({'quiet_from': 99999, 'replies': 'yes'}), const NotifyPrefs());
  });

  test('quiet hours across midnight, and inside one day', () {
    const night = NotifyPrefs(quietOn: true, quietFrom: 23 * 60, quietTo: 7 * 60);
    expect(night.isQuietAt(23 * 60 + 30), isTrue);
    expect(night.isQuietAt(6 * 60), isTrue);
    expect(night.isQuietAt(12 * 60), isFalse);
    const lunch = NotifyPrefs(quietOn: true, quietFrom: 13 * 60, quietTo: 14 * 60);
    expect(lunch.isQuietAt(13 * 60 + 5), isTrue);
    expect(lunch.isQuietAt(14 * 60), isFalse);
    expect(const NotifyPrefs(quietFrom: 0, quietTo: 1439).isQuietAt(5), isFalse); // switched off
  });

  test('"23:00" for a minute of the day', () {
    expect(clockText(23 * 60), '23:00');
    expect(clockText(7 * 60 + 5), '07:05');
  });
}
