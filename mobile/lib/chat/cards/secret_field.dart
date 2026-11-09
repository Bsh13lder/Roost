import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import 'card_base.dart';

/// The server's SECRET_VALUE_MAX_CHARS.
const secretMaxChars = 256;

String secretExplanation(String host, String kind, String botName) =>
    "Type your $host $kind; it goes straight into the box on $botName's computer. The bot never sees it.";

/// The Sign-in card's masked field (B3; on the phone since owner, 2026-11-05,
/// "like Grok: a small field in the chat for my id, password or code"). The
/// value lives only in this field, goes to the server on Send, and the field
/// empties at once whatever the answer.
class SecretField extends StatefulWidget {
  const SecretField(
      {super.key,
      required this.host,
      required this.kind,
      required this.botName,
      required this.busy,
      required this.onSend});

  final String host, kind, botName;
  final bool busy;
  /// The value, and for a password whether Save in Vault is ticked (null for
  /// a code, which is never saved).
  final Future<void> Function(String value, bool? save) onSend;

  @override
  State<SecretField> createState() => _SecretFieldState();
}

class _SecretFieldState extends State<SecretField> {
  final _text = TextEditingController();

  /// Save in Vault (owner, 2026-11-08): on by default, for a password only.
  bool _save = true;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  void _send() {
    final typed = _text.text;
    _text.clear();
    setState(() {});
    if (typed.isNotEmpty) widget.onSend(typed, widget.kind == 'password' ? _save : null);
  }

  @override
  Widget build(BuildContext context) {
    final code = widget.kind == 'code';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(secretExplanation(widget.host, widget.kind, widget.botName),
          style: const TextStyle(color: Tokens.textSecondary)),
      const SizedBox(height: Tokens.space2),
      Row(children: [
        Expanded(
          child: TextField(
            key: const Key('secret-field'),
            controller: _text,
            obscureText: true,
            enableSuggestions: false,
            autocorrect: false,
            enabled: !widget.busy,
            maxLength: secretMaxChars,
            keyboardType: code ? TextInputType.number : TextInputType.visiblePassword,
            autofillHints: [code ? AutofillHints.oneTimeCode : AutofillHints.password],
            decoration: InputDecoration(
                isDense: true, counterText: '', hintText: 'Your ${widget.kind}'),
            onChanged: (_) => setState(() {}),
            onSubmitted: (_) => _send(),
          ),
        ),
        const SizedBox(width: Tokens.space2),
        CardButton('Send',
            primary: true,
            onPressed: widget.busy || _text.text.isEmpty ? null : _send),
      ]),
      if (!code)
        CheckboxListTile(
          key: const Key('secret-save'),
          dense: true,
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          title: const Text('Save in Vault'),
          value: _save,
          onChanged: widget.busy ? null : (v) => setState(() => _save = v ?? false),
        ),
    ]);
  }
}
