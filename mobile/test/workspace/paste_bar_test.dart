import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/workspace/bar/paste_catch.dart';
import 'package:roost_mobile/workspace/workspace_screen.dart';

import '../fake_adapter.dart';
import 'workspace_fakes.dart';

const pastedText = 'Buy milk !high\nPack\n  Socks\n  Shoes\n';

Map<String, Object?> pastedReading({bool ready = true}) => {
      'count': 2,
      'ready': ready,
      'problem': ready ? null : 'Line 2: Which project?',
      'tasks': [
        {'title': 'Buy milk', 'ready': true, 'priority': 'high', 'steps': <String>[]},
        {'title': 'Pack', 'ready': ready, 'steps': ['Socks', 'Shoes']},
      ],
    };

/// Answers parse-many (ready or not) and records each created task.
ExtraAnswer pasteAnswer(List<Map<String, dynamic>> created, {bool ready = true}) =>
    (RequestOptions o) {
      if (o.method == 'POST' && o.uri.path == '/api/tasks/parse-many') {
        return FakeAdapter.json(pastedReading(ready: ready));
      }
      if (o.method == 'POST' && o.uri.path == '/api/tasks') {
        final body = (o.data as Map).cast<String, dynamic>();
        created.add(body);
        return FakeAdapter.json(wtask('n${created.length}', body['title'] as String), status: 201);
      }
      return null;
    };

void setClipboard(WidgetTester tester, String text) {
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'Clipboard.getData') return {'text': text};
    if (call.method == 'Clipboard.hasStrings') return {'value': true};
    return null;
  });
  addTearDown(() => tester.binding.defaultBinaryMessenger
      .setMockMethodCallHandler(SystemChannels.platform, null));
}

Future<void> pasteByKeys(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('work-bar')));
  await tester.pumpAndSettle();
  await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
  await tester.sendKeyEvent(LogicalKeyboardKey.keyV);
  await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
  await tester.pumpAndSettle();
}

String barText(WidgetTester tester) =>
    tester.widget<TextField>(find.byKey(const Key('work-bar'))).controller!.text;

void main() {
  test('a one-line paste replaces the selection, on one line, within the limit', () {
    const value = TextEditingValue(
      text: 'Call  today',
      selection: TextSelection.collapsed(offset: 5),
    );
    final next = pasteInto(value, 'Ana\r\n', 300);
    expect(next.text, 'Call Ana today');
    expect(next.selection.baseOffset, 8);
    final cut = pasteInto(const TextEditingValue(text: 'ab'), 'cdefg', 4);
    expect(cut.text, 'abcd');
    final picked = pasteInto(
      const TextEditingValue(text: 'Buy eggs', selection: TextSelection(baseOffset: 4, extentOffset: 8)),
      'milk',
      300,
    );
    expect(picked.text, 'Buy milk');
  });

  testWidgets('pasting several lines offers "Add 2 tasks" and adds each one', (tester) async {
    final created = <Map<String, dynamic>>[];
    final a = await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: pasteAnswer(created));
    setClipboard(tester, pastedText);
    await pasteByKeys(tester);

    final parse = a.requests.lastWhere((r) => r.uri.path == '/api/tasks/parse-many');
    expect(parse.data, {'text': pastedText});
    expect(find.text('Add 2 tasks?'), findsOneWidget);
    expect(find.text('Buy milk'), findsWidgets);
    expect(find.text('2 steps'), findsOneWidget);
    expect(barText(tester), isEmpty);

    await tester.tap(find.byKey(const Key('paste-add')));
    await tester.pumpAndSettle();
    expect(created, [
      {'title': 'Buy milk', 'priority': 'high'},
      {'title': 'Pack', 'steps': ['Socks', 'Shoes']},
    ]);
    expect(find.text('Add 2 tasks?'), findsNothing);
    expect(find.text('Added 2 tasks'), findsOneWidget);
  });

  testWidgets('a list with a problem names it and adds nothing; Cancel closes', (tester) async {
    final created = <Map<String, dynamic>>[];
    await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: pasteAnswer(created, ready: false));
    setClipboard(tester, pastedText);
    await pasteByKeys(tester);
    expect(find.text('Line 2: Which project?'), findsOneWidget);
    final add = tester.widget<FilledButton>(find.byKey(const Key('paste-add')));
    expect(add.onPressed, isNull);
    await tester.tap(find.byKey(const Key('paste-cancel')));
    await tester.pumpAndSettle();
    expect(find.text('Add 2 tasks?'), findsNothing);
    expect(created, isEmpty);
  });

  testWidgets('Paste from the field\'s menu offers the list too', (tester) async {
    final created = <Map<String, dynamic>>[];
    await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: pasteAnswer(created));
    setClipboard(tester, pastedText);
    await tester.longPress(find.byKey(const Key('work-bar')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Paste'));
    await tester.pumpAndSettle();
    expect(find.text('Add 2 tasks?'), findsOneWidget);
  });

  testWidgets('pasting one line just types it', (tester) async {
    final a = await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: pasteAnswer([]));
    setClipboard(tester, 'Call Ana\n');
    await pasteByKeys(tester);
    expect(barText(tester), 'Call Ana');
    expect(a.requests.where((r) => r.uri.path == '/api/tasks/parse-many'), isEmpty);
  });

  testWidgets('on a 320 dp phone the picker row and the bar never overflow', (tester) async {
    await pumpWorkspace(tester, const WorkspaceScreen(), [],
        size: const Size(960, 2000), extra: pasteAnswer([]));
    await tester.enterText(find.byKey(const Key('work-bar')), 'Call Ana friday');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('qp-date')), findsOneWidget);
    expect(tester.takeException(), isNull);
    final row = tester.getRect(find.byKey(const Key('qp-row')));
    expect(row.right, lessThanOrEqualTo(320));
    for (final id in ['date', 'project', 'priority', 'help']) {
      final rect = tester.getRect(find.byKey(Key('qp-$id')));
      expect(rect.left, greaterThanOrEqualTo(0), reason: id);
      expect(rect.right, lessThanOrEqualTo(320), reason: id);
    }
  });

  testWidgets('a wide phone keeps the pickers on one line', (tester) async {
    await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: pasteAnswer([]));
    await tester.enterText(find.byKey(const Key('work-bar')), 'Call Ana');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    final date = tester.getRect(find.byKey(const Key('qp-date')));
    final project = tester.getRect(find.byKey(const Key('qp-project')));
    expect(project.top, date.top);
    expect(tester.takeException(), isNull);
  });
}
