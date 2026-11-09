import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/board/notes/note_editor.dart';

import '../fake_adapter.dart';

Map<String, Object?> note(String content, int revision) => {
      'id': 'n1',
      'title': 'Plan',
      'content': content,
      'snippet': content,
      'revision': revision,
      'tags': <String>[],
      'links': <Object>[],
    };

void main() {
  testWidgets('a save with a stale revision shows Changed elsewhere',
      (tester) async {
    final bodies = <Object?>[];
    final adapter = FakeAdapter((o) {
      if (o.method == 'GET' && o.path == '/api/notes/n1') {
        return FakeAdapter.json(note('mine', 3));
      }
      if (o.method == 'PUT' && o.path == '/api/notes/n1') {
        bodies.add(o.data);
        if (bodies.length == 1) {
          return FakeAdapter.json(
              {'detail': 'conflict', 'current': note('theirs', 4)},
              status: 409);
        }
        return FakeAdapter.json(note('mine edited', 5));
      }
      fail('unexpected ${o.method} ${o.path}');
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: NoteEditorScreen(noteId: 'n1')),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(bodies.first, containsPair('base_revision', 3));
    expect(find.text('Changed elsewhere'), findsOneWidget);
    expect(find.textContaining('theirs'), findsOneWidget);

    await tester.tap(find.text('Keep mine'));
    await tester.pump();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(bodies.last, containsPair('base_revision', 4));
    expect(find.text('Changed elsewhere'), findsNothing);
  });
}
