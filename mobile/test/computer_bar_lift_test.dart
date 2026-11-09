import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/computer/computer_screen.dart';

void main() {
  test('the bottom bar rises above the phone keyboard for its own forms', () {
    expect(barLift(320, remoteKeys: false), 320);
    expect(barLift(0, remoteKeys: false), 0);
  });

  test('while typing on the remote computer the bar stays put', () {
    expect(barLift(320, remoteKeys: true), 0);
  });
}
