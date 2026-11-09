import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/notify/local_alerts.dart';
import 'package:roost_mobile/notify/stay_connected.dart';
import 'package:roost_mobile/theme/tokens.dart';

const res = 'android/app/src/main/res';

String hex(int argb) =>
    '#${(argb & 0xFFFFFF).toRadixString(16).padLeft(6, '0').toUpperCase()}';

const legacySizes = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192};
const adaptive108 = {'mdpi': 1.0, 'hdpi': 1.5, 'xhdpi': 2.0, 'xxhdpi': 3.0, 'xxxhdpi': 4.0};

(int, int) pngSize(List<int> png) {
  final b = ByteData.sublistView(Uint8List.fromList(png));
  return (b.getUint32(16), b.getUint32(20));
}

void main() {
  test('the app is called Roost and uses its own launcher icon', () {
    final manifest =
        File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
    expect(manifest, contains('android:label="Roost"'));
    expect(manifest, contains('android:icon="@mipmap/ic_launcher"'));
  });

  test('Android 8+ gets an adaptive icon: Gela on the dark background', () {
    final adaptive =
        File('$res/mipmap-anydpi-v26/ic_launcher.xml').readAsStringSync();
    expect(adaptive, contains('<adaptive-icon'));
    expect(adaptive, contains('@color/ic_launcher_background'));
    expect(adaptive, contains('@drawable/ic_launcher_foreground'));

    final colors = File('$res/values/ic_launcher_colors.xml').readAsStringSync();
    expect(colors.toUpperCase(), contains(hex(Tokens.bg.toARGB32())));

    // The foreground is PNGs drawn by test/tool/make_icons_test.dart, 108 dp a side.
    expect(File('$res/drawable/ic_launcher_foreground.xml').existsSync(), isFalse);
    for (final MapEntry(key: dpi, value: d) in adaptive108.entries) {
      final png = File('$res/drawable-$dpi/ic_launcher_foreground.png');
      expect(pngSize(png.readAsBytesSync()), ((108 * d).round(), (108 * d).round()), reason: dpi);
    }
  });

  test('older Android versions get the same robot as PNGs, at their sizes', () {
    for (final MapEntry(key: dpi, value: px) in legacySizes.entries) {
      final png = File('$res/mipmap-$dpi/ic_launcher.png').readAsBytesSync();
      expect(pngSize(png), (px, px), reason: dpi);
    }
  });

  test('notifications use a white silhouette, never the colour launcher icon', () {
    final icon = File('$res/drawable/ic_stat_roost.xml').readAsStringSync();
    final fills = RegExp(r'fillColor="([^"]+)"').allMatches(icon).map((m) => m.group(1)).toSet();
    expect(fills, {'#FFFFFFFF'});
    expect(alertIcon, '@drawable/ic_stat_roost');
    final manifest = File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
    expect(manifest, contains('android:name="$stayConnectedIconMeta"'));
    expect(manifest, contains('@drawable/ic_stat_roost'));
    expect(File('$res/raw/keep.xml').readAsStringSync(), contains('@drawable/ic_stat_roost'));
  });
}
