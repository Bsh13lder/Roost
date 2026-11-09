import 'package:flutter/material.dart';

import '../theme/tokens.dart';
import 'computer_api.dart';

const keepQuestion = 'Keep me signed in on this computer?';
const neverSees = 'Roost never sees your password.';

/// "Which account did you use?" (optional), and on a Sign-in card "Keep me
/// signed in on this computer?". The label is kept in Vault: site logins,
/// never a password.
class GiveBackForm extends StatefulWidget {
  const GiveBackForm({
    super.key,
    required this.host,
    required this.signIn,
    required this.busy,
    required this.error,
    required this.onConfirm,
    required this.onBack,
  });

  final String? host;
  final bool signIn;
  final bool busy;
  final String? error;
  final void Function(String? account, bool? keep) onConfirm;
  final VoidCallback onBack;

  @override
  State<GiveBackForm> createState() => _GiveBackFormState();
}

class _GiveBackFormState extends State<GiveBackForm> {
  final _account = TextEditingController();
  bool _tooLong = false;

  @override
  void dispose() {
    _account.dispose();
    super.dispose();
  }

  void _confirm(bool? keep) {
    final label = _account.text.trim();
    if (label.length > accountMaxChars) {
      setState(() => _tooLong = true);
      return;
    }
    setState(() => _tooLong = false);
    widget.onConfirm(label.isEmpty ? null : label, keep);
  }

  @override
  Widget build(BuildContext context) {
    final host = widget.host;
    final hint = [
      if (host != null && host.isNotEmpty)
        'Saved for $host, so the bot knows which one it is signed in with.',
      if (widget.signIn) neverSees,
    ].join(' ');
    return Column(mainAxisSize: MainAxisSize.min, children: [
      TextField(
        controller: _account,
        enabled: !widget.busy,
        autocorrect: false,
        decoration: InputDecoration(
          labelText: 'Which account did you use? (optional)',
          helperText: hint.isEmpty ? null : hint,
          helperMaxLines: 3,
          errorText: _tooLong
              ? 'Keep the account to $accountMaxChars characters or fewer.'
              : widget.error,
        ),
        onSubmitted: (_) => _confirm(widget.signIn ? true : null),
      ),
      const SizedBox(height: Tokens.space2),
      if (widget.signIn) ...[
        const Align(
            alignment: Alignment.centerLeft,
            child: Text(keepQuestion,
                style: TextStyle(color: Tokens.textSecondary))),
        const SizedBox(height: Tokens.space1),
      ],
      Wrap(spacing: Tokens.space2, children: [
        if (widget.signIn) ...[
          FilledButton(
              onPressed: widget.busy ? null : () => _confirm(true),
              child: const Text('Yes, keep me signed in')),
          OutlinedButton(
              onPressed: widget.busy ? null : () => _confirm(false),
              child: const Text('No, this time')),
        ] else
          FilledButton(
              onPressed: widget.busy ? null : () => _confirm(null),
              child: const Text('Give it back')),
        TextButton(
            onPressed: widget.busy ? null : widget.onBack,
            child: const Text('Back')),
      ]),
    ]);
  }
}

/// "I'm done teaching": an optional line on what the task is, then the bot
/// drafts a skill you Save or not. Only clicks and field names were recorded.
class TeachDoneForm extends StatefulWidget {
  const TeachDoneForm({
    super.key,
    required this.busy,
    required this.error,
    required this.onConfirm,
    required this.onDiscard,
    required this.onBack,
  });

  final bool busy;
  final String? error;
  final void Function(String? description) onConfirm;
  final VoidCallback onDiscard;
  final VoidCallback onBack;

  @override
  State<TeachDoneForm> createState() => _TeachDoneFormState();
}

class _TeachDoneFormState extends State<TeachDoneForm> {
  final _text = TextEditingController();
  bool _tooLong = false;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  void _make() {
    final t = _text.text.trim();
    if (t.length > teachDescriptionMax) {
      setState(() => _tooLong = true);
      return;
    }
    widget.onConfirm(t.isEmpty ? null : t);
  }

  @override
  Widget build(BuildContext context) {
    return Column(mainAxisSize: MainAxisSize.min, children: [
      TextField(
        controller: _text,
        enabled: !widget.busy,
        decoration: InputDecoration(
          labelText: 'What is this task? (optional)',
          helperText:
              'The bot turns what you showed into a skill. Nothing is saved until you press Save skill in the chat.',
          helperMaxLines: 3,
          errorText: _tooLong
              ? 'Keep it to $teachDescriptionMax characters or fewer.'
              : widget.error,
        ),
        onSubmitted: (_) => _make(),
      ),
      const SizedBox(height: Tokens.space2),
      Wrap(spacing: Tokens.space2, children: [
        FilledButton(
            onPressed: widget.busy ? null : _make,
            child: const Text('Make the skill')),
        TextButton(
            onPressed: widget.busy ? null : widget.onDiscard,
            child: const Text('Discard')),
        TextButton(
            onPressed: widget.busy ? null : widget.onBack,
            child: const Text('Back')),
      ]),
    ]);
  }
}
