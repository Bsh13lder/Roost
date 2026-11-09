import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/projects/project_edit.dart';

void main() {
  test('an amount is read as the server wants it, or refused', () {
    expect(readAmount('12,5'), '12.50');
    expect(readAmount(' 1200 '), '1200.00');
    expect(readAmount('0'), isNull);
    expect(readAmount('12.345'), isNull);
    expect(readAmount('abc'), isNull);
    expect(readAmount('-3'), isNull);
  });
}
