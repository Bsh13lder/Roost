import 'package:flutter/material.dart';

import '../theme/tokens.dart';
import 'keysyms.dart';

const _sentinel = '​';

/// The system keyboard as key events. A one-character sentinel stays in an
/// invisible field so a backspace is seen; each edit is turned into key presses
/// and the field is put back. Nothing typed is kept, logged or shown. The bar
/// is a slim strip of extra keys that sits on top of the phone's keyboard.
class KeyboardBar extends StatefulWidget {
  const KeyboardBar({super.key, required this.onKey, this.onHide});

  /// A whole key press (down and up).
  final void Function(int keysym) onKey;

  /// Closes the keyboard (the strip's last button).
  final VoidCallback? onHide;

  @override
  State<KeyboardBar> createState() => _KeyboardBarState();
}

class _KeyboardBarState extends State<KeyboardBar> {
  final _controller = TextEditingController(text: _sentinel);

  @override
  void initState() {
    super.initState();
    _reset();
  }

  void _reset() => _controller.value = const TextEditingValue(
      text: _sentinel, selection: TextSelection.collapsed(offset: 1));

  void _changed(String after) {
    final keys = diffToKeys(_sentinel, after);
    for (var i = 0; i < keys.backspaces; i++) {
      widget.onKey(keyBackspace);
    }
    keys.keysyms.forEach(widget.onKey);
    _reset();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Tokens.panel.withValues(alpha: 0.92),
      child: SizedBox(
        height: 44,
        child: Row(children: [
          // The invisible field that takes the phone's keyboard.
          SizedBox(width: 1, height: 1, child: Opacity(opacity: 0, child: _field())),
          Expanded(
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Tokens.space2),
              children: [
                for (final (label, sym) in const [
                  ('Esc', keyEscape),
                  ('Tab', keyTab),
                  ('←', keyLeft),
                  ('↑', keyUp),
                  ('↓', keyDown),
                  ('→', keyRight),
                  ('⏎', keyReturn),
                ])
                  _key(label, () => widget.onKey(sym)),
              ],
            ),
          ),
          if (widget.onHide != null)
            IconButton(
              key: const Key('keyboard-hide'),
              tooltip: 'Hide keyboard',
              icon: const Icon(Icons.keyboard_hide, size: 20),
              onPressed: widget.onHide,
            ),
        ]),
      ),
    );
  }

  Widget _key(String label, VoidCallback onTap) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 6),
        child: TextButton(
          style: TextButton.styleFrom(
            minimumSize: const Size(40, 32),
            padding: const EdgeInsets.symmetric(horizontal: Tokens.space2),
            backgroundColor: Tokens.bg.withValues(alpha: 0.6),
            foregroundColor: Tokens.text,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          ),
          onPressed: onTap,
          child: Text(label),
        ),
      );

  Widget _field() => TextField(
        controller: _controller,
        autofocus: true,
        autocorrect: false,
        enableSuggestions: false,
        enableInteractiveSelection: false,
        showCursor: false,
        keyboardType: TextInputType.visiblePassword,
        textInputAction: TextInputAction.send,
        style: const TextStyle(color: Colors.transparent, fontSize: 1),
        decoration: const InputDecoration.collapsed(hintText: ''),
        onChanged: _changed,
        onSubmitted: (_) => widget.onKey(keyReturn),
      );
}
