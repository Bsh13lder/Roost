import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/app.dart';
import 'package:roost_mobile/app_version.dart';
import 'package:roost_mobile/features/home/home_screen.dart';
import 'package:roost_mobile/features/settings/settings_screen.dart';
import 'package:roost_mobile/live/live_connection.dart';
import 'package:roost_mobile/update/installer.dart';
import 'package:roost_mobile/update/release.dart';
import 'package:roost_mobile/update/update_banner.dart';
import 'package:roost_mobile/update/update_controller.dart';

import '../fake_adapter.dart';
import '../offline_test.dart' show QuietLive, homeAnswer;

/// What the fake adapter sends for the APK: its body is JSON-encoded, so the
/// bytes on disk are `"apk-bytes"` with the quotes.
const apkBody = 'apk-bytes';
final apkSha = sha256.convert(utf8.encode(jsonEncode(apkBody))).toString();

Map<String, Object?> latest({int build = 2, String? sha}) => {
      'version': '1.0.$build',
      'build': build,
      'file': 'roost-1.0.$build+$build.apk',
      'sha256': sha ?? apkSha,
      'notes': 'Update check inside the app',
    };

class FakeInstaller implements UpdateInstaller {
  FakeInstaller(this.dir, {this.allowed = true});

  final Directory dir;
  bool allowed;
  final installed = <String>[];
  int settingsOpened = 0;

  @override
  Future<String> cacheDir() async => dir.path;

  @override
  Future<bool> canInstall() async => allowed;

  @override
  Future<void> openInstallSettings() async => settingsOpened++;

  @override
  Future<void> install(String path) async => installed.add(path);
}

FakeAdapter serving(Map<String, Object?>? release) => FakeAdapter((o) {
      if (o.uri.path == '/api/mobile/latest') {
        return release == null
            ? FakeAdapter.json(
                {'detail': 'No app update has been published yet.'},
                status: 404)
            : FakeAdapter.json(release);
      }
      if (o.uri.path.startsWith('/api/mobile/apk/')) {
        return FakeAdapter.json(apkBody);
      }
      return FakeAdapter.json({});
    });

ProviderContainer container(FakeAdapter adapter, FakeInstaller installer,
    {int ownBuild = 1}) {
  final c = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()
      ..url = 'http://127.0.0.1:18800'
      ..token = 'tok'),
    httpAdapterProvider.overrideWithValue(adapter),
    installerProvider.overrideWithValue(installer),
    ownBuildProvider.overrideWithValue(ownBuild),
  ]);
  return c;
}

Future<void> signedIn(ProviderContainer c) async {
  c.read(authProvider);
  while (!c.read(authProvider).ready) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  late Directory tmp;
  setUp(() async => tmp = await Directory.systemTemp.createTemp('roost-up-'));
  tearDown(() async => tmp.delete(recursive: true));

  group('versions', () {
    test('the build number is read from the app version', () {
      expect(buildNumberOf('1.0.1+2'), 2);
      expect(buildNumberOf('1.0.0'), 0);
      expect(buildNumberOf('junk+x'), 0);
      expect(buildNumberOf(appVersion), greaterThanOrEqualTo(2));
    });

    test('only a higher build is newer', () {
      final r = Release.fromJson(latest(build: 3))!;
      expect(r.isNewerThan(2), isTrue);
      expect(r.isNewerThan(3), isFalse);
      expect(r.isNewerThan(4), isFalse);
    });

    test('a bad release answer reads as none', () {
      expect(Release.fromJson([]), isNull);
      expect(Release.fromJson({...latest(), 'file': '../x.apk'}), isNull);
      expect(Release.fromJson({...latest(), 'sha256': 'abc'}), isNull);
      expect(Release.fromJson({...latest(), 'build': '2'}), isNull);
    });
  });

  group('check and install', () {
    test('a newer build is offered, the same build is not', () async {
      final c = container(serving(latest()), FakeInstaller(tmp));
      addTearDown(c.dispose);
      await signedIn(c);
      await c.read(updateProvider.notifier).check();
      expect(c.read(updateProvider).available?.version, '1.0.2');

      final same = container(serving(latest()), FakeInstaller(tmp), ownBuild: 2);
      addTearDown(same.dispose);
      await signedIn(same);
      await same.read(updateProvider.notifier).check();
      expect(same.read(updateProvider).available, isNull);
      expect(same.read(updateProvider).upToDate, isTrue);
    });

    test('nothing published is not an error', () async {
      final c = container(serving(null), FakeInstaller(tmp));
      addTearDown(c.dispose);
      await signedIn(c);
      await c.read(updateProvider.notifier).check();
      expect(c.read(updateProvider).available, isNull);
      expect(c.read(updateProvider).error, isNull);
    });

    test('install downloads with the session, checks the sha, then installs',
        () async {
      final adapter = serving(latest());
      final installer = FakeInstaller(tmp);
      final c = container(adapter, installer);
      addTearDown(c.dispose);
      await signedIn(c);
      await c.read(updateProvider.notifier).check();
      await c.read(updateProvider.notifier).install();
      final get = adapter.requests.last;
      expect(get.uri.path, '/api/mobile/apk/roost-1.0.2+2.apk');
      expect(get.headers['Cookie'], contains('tok'));
      expect(installer.installed, ['${tmp.path}/roost-1.0.2+2.apk']);
      expect(c.read(updateProvider).error, isNull);
    });

    test('a sha mismatch refuses to install and removes the file', () async {
      final installer = FakeInstaller(tmp);
      final c = container(serving(latest(sha: 'f' * 64)), installer);
      addTearDown(c.dispose);
      await signedIn(c);
      await c.read(updateProvider.notifier).check();
      await c.read(updateProvider.notifier).install();
      expect(installer.installed, isEmpty);
      expect(c.read(updateProvider).error, damagedDownloadMessage);
      expect(File('${tmp.path}/roost-1.0.2+2.apk').existsSync(), isFalse);
    });

    test('without the install permission it opens that setting and explains',
        () async {
      final installer = FakeInstaller(tmp, allowed: false);
      final c = container(serving(latest()), installer);
      addTearDown(c.dispose);
      await signedIn(c);
      await c.read(updateProvider.notifier).check();
      await c.read(updateProvider.notifier).install();
      expect(installer.settingsOpened, 1);
      expect(installer.installed, isEmpty);
      expect(c.read(updateProvider).note, installPermissionMessage);
    });
  });

  group('screens', () {
    late SwitchAdapter adapter;

    Future<ProviderContainer> pumpHome(
        WidgetTester tester, Map<String, Object?>? release) async {
      tester.view.physicalSize = const Size(1080, 3600);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      adapter = SwitchAdapter((o) => o.uri.path == '/api/mobile/latest'
          ? (release == null
              ? FakeAdapter.json({'detail': 'none'}, status: 404)
              : FakeAdapter.json(release))
          : homeAnswer(o));
      final c = ProviderContainer(overrides: [
        sessionStoreProvider.overrideWithValue(MemorySessionStore()
          ..url = 'http://127.0.0.1:18800'
          ..token = 'tok'),
        httpAdapterProvider.overrideWithValue(adapter),
        liveProvider.overrideWith(QuietLive.new),
        installerProvider.overrideWithValue(FakeInstaller(tmp)),
        ownBuildProvider.overrideWithValue(1),
      ]);
      addTearDown(c.dispose);
      await tester.pumpWidget(
          UncontrolledProviderScope(container: c, child: const RoostApp()));
      await tester.pumpAndSettle();
      return c;
    }

    testWidgets('Home shows the banner when a newer build is published',
        (tester) async {
      await pumpHome(tester, latest());
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(find.byKey(const Key('update-banner')), findsOneWidget);
      expect(find.text('Update available · 1.0.2'), findsOneWidget);
      expect(find.byKey(const Key('update-install')), findsOneWidget);
    });

    testWidgets('Home has no banner when nothing newer is published',
        (tester) async {
      await pumpHome(tester, null);
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(find.byType(UpdateBanner, skipOffstage: false), findsOneWidget);
      expect(find.byKey(const Key('update-banner')), findsNothing);
    });

    testWidgets('Settings has a Check for updates row that shows the update',
        (tester) async {
      await pumpHome(tester, latest());
      await tester.tap(find.byKey(const Key('initials')));
      await tester.pumpAndSettle();
      expect(find.byType(SettingsScreen), findsOneWidget);
      final row = find.byKey(const Key('settings-update'));
      await tester.dragUntilVisible(
          row, find.byType(ListView), const Offset(0, -100));
      expect(find.text('Install 1.0.2'), findsOneWidget);
    });

    testWidgets('Settings says up to date after a check finds nothing newer',
        (tester) async {
      await pumpHome(tester, null);
      await tester.tap(find.byKey(const Key('initials')));
      await tester.pumpAndSettle();
      final row = find.byKey(const Key('settings-update'));
      await tester.dragUntilVisible(
          row, find.byType(ListView), const Offset(0, -100));
      expect(find.text('Check for updates'), findsOneWidget);
      int checks() => adapter.requests
          .where((r) => r.uri.path == '/api/mobile/latest')
          .length;
      final before = checks();
      await tester.ensureVisible(row);
      await tester.tap(row);
      await tester.pumpAndSettle();
      expect(checks(), before + 1);
      expect(find.text('Up to date'), findsOneWidget);
    });
  });
}
