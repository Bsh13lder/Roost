import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/profile/picture_row.dart';

void main() {
  test('a picture is known by its first bytes, not its name', () {
    expect(
        pictureMime(
            Uint8List.fromList([0x89, 0x50, 0x4E, 0x47, 13, 10, 26, 10, 0])),
        'image/png');
    expect(pictureMime(Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0])),
        'image/jpeg');
    expect(
        pictureMime(Uint8List.fromList(
            [0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x45, 0x42, 0x50])),
        'image/webp');
    expect(pictureMime(Uint8List.fromList([1, 2, 3])), isNull);
  });
}
