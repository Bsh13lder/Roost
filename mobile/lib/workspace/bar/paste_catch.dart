import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// A one-line field drops a pasted list's line breaks before anyone sees
/// them, so the bar reads the clipboard itself: from the field's Paste
/// button and from Ctrl+V / Cmd+V.
class _PasteIntent extends Intent {
  const _PasteIntent();
}

/// Wraps [child] (the field) so Ctrl+V and Cmd+V call [onPaste].
class PasteCatcher extends StatelessWidget {
  const PasteCatcher({super.key, required this.onPaste, required this.child});

  final VoidCallback onPaste;
  final Widget child;

  @override
  Widget build(BuildContext context) => Shortcuts(
        shortcuts: const {
          SingleActivator(LogicalKeyboardKey.keyV, control: true): _PasteIntent(),
          SingleActivator(LogicalKeyboardKey.keyV, meta: true): _PasteIntent(),
        },
        child: Actions(
          actions: {
            _PasteIntent: CallbackAction<_PasteIntent>(onInvoke: (_) {
              onPaste();
              return null;
            }),
          },
          child: child,
        ),
      );
}

/// The field's long-press menu, its Paste button calling [onPaste].
EditableTextContextMenuBuilder pasteMenu(VoidCallback onPaste) =>
    (context, state) => AdaptiveTextSelectionToolbar.buttonItems(
          anchors: state.contextMenuAnchors,
          buttonItems: [
            for (final item in state.contextMenuButtonItems)
              item.type == ContextMenuButtonType.paste
                  ? item.copyWith(onPressed: () {
                      state.hideToolbar();
                      onPaste();
                    })
                  : item,
          ],
        );

/// [value] with [pasted] in place of its selection, on one line and at
/// most [maxLength] long; the caret after the pasted words.
TextEditingValue pasteInto(TextEditingValue value, String pasted, int maxLength) {
  final line = pasted.replaceAll(RegExp(r'[\r\n]+'), ' ').trim();
  final sel = value.selection.isValid
      ? value.selection
      : TextSelection.collapsed(offset: value.text.length);
  final before = value.text.substring(0, sel.start);
  final after = value.text.substring(sel.end);
  final room = maxLength - before.length - after.length;
  final kept = room <= 0 ? '' : (line.length > room ? line.substring(0, room) : line);
  return TextEditingValue(
    text: '$before$kept$after',
    selection: TextSelection.collapsed(offset: before.length + kept.length),
  );
}
