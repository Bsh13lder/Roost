import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/common/widgets.dart';

// Owner, 2026-10-26: "Done task stuck like that". Flutter keeps a bar with an
// action until it is tapped unless the bar says otherwise.
void main() {
  testWidgets('a bar with Undo goes away by itself', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => snack(context, 'Done: Go to sleep',
                action: 'Undo', onAction: () {}),
            child: const Text('go'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();
    expect(find.text('Done: Go to sleep'), findsOneWidget);
    await tester.pump(const Duration(seconds: 6));
    await tester.pumpAndSettle();
    expect(find.text('Done: Go to sleep'), findsNothing);
  });
}
