import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../chat/cards/secret_field.dart' show secretMaxChars;
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'vault_models.dart';
import 'vault_repo.dart';

const savedInVaultText = 'Saved in Vault: passwords';
const _retryText = 'Type the password again to retry.';

/// The server's VAULT_HOST_MAX_CHARS, VAULT_USERNAME_MAX_CHARS and
/// VAULT_PASSWORD_MAX_CHARS.
const vaultHostMaxChars = 253;
const vaultUsernameMaxChars = 254;
const vaultPasswordMaxChars = secretMaxChars;

/// Save a password (owner, 2026-11-08), from Settings' Add and the chat's +
/// menu: site, user name and a masked password, posted to Vault: passwords
/// only, never to a chat. True when saved; a snack bar then says so.
Future<bool> showSavePasswordSheet(BuildContext context) async {
  final messenger = ScaffoldMessenger.of(context);
  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Tokens.panel,
    builder: (_) => const SavePasswordSheet(),
  );
  if (saved != true) return false;
  messenger.showSnackBar(const SnackBar(content: Text(savedInVaultText)));
  return true;
}

class SavePasswordSheet extends ConsumerStatefulWidget {
  const SavePasswordSheet({super.key});

  @override
  ConsumerState<SavePasswordSheet> createState() => _SavePasswordSheetState();
}

class _SavePasswordSheetState extends ConsumerState<SavePasswordSheet> {
  final _site = TextEditingController();
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    // The password lives only in this field, and goes with the sheet.
    _password.clear();
    for (final c in [_site, _username, _password]) {
      c.dispose();
    }
    super.dispose();
  }

  bool get _ready => _site.text.trim().isNotEmpty && _password.text.isNotEmpty;

  Future<void> _save() async {
    if (!_ready || _busy) return;
    final login = NewLogin(
        host: _site.text.trim(), username: _username.text.trim(), password: _password.text);
    // Gone from the field before the call starts.
    _password.clear();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(vaultPasswordsRepoProvider).save(login);
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '${describe(e)} $_retryText');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
        child: SafeArea(
          child: AutofillGroup(
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(Tokens.space4),
              children: [
                const Text('Save a password', style: TextStyle(fontSize: Tokens.fsLead)),
                const SizedBox(height: Tokens.space2),
                _field(_site, 'vault-site', 'Site (such as upwork.com)', vaultHostMaxChars,
                    keyboard: TextInputType.url, hints: const [AutofillHints.url]),
                _field(_username, 'vault-username', 'User name or email', vaultUsernameMaxChars,
                    keyboard: TextInputType.emailAddress, hints: const [AutofillHints.username]),
                _passwordField(),
                if (_error != null) Quiet(_error!, bad: true),
                const Quiet('Your bots never see it.'),
                Row(children: [
                  const Spacer(),
                  TextButton(
                      onPressed: _busy ? null : () => Navigator.of(context).pop(false),
                      child: const Text('Cancel')),
                  const SizedBox(width: Tokens.space2),
                  FilledButton(
                      key: const Key('vault-save'),
                      onPressed: _busy || !_ready ? null : _save,
                      child: const Text('Save')),
                ]),
              ],
            ),
          ),
        ),
      );

  Widget _passwordField() => Padding(
        padding: const EdgeInsets.only(bottom: Tokens.space2),
        child: TextField(
          key: const Key('vault-password'),
          controller: _password,
          obscureText: true,
          enableSuggestions: false,
          autocorrect: false,
          enableIMEPersonalizedLearning: false,
          maxLength: vaultPasswordMaxChars,
          keyboardType: TextInputType.visiblePassword,
          autofillHints: const [AutofillHints.newPassword],
          decoration: const InputDecoration(labelText: 'Password', counterText: ''),
          onChanged: (_) => setState(() {}),
          onSubmitted: (_) => _save(),
        ),
      );

  Widget _field(TextEditingController c, String key, String label, int max,
          {TextInputType? keyboard, List<String>? hints}) =>
      Padding(
        padding: const EdgeInsets.only(bottom: Tokens.space2),
        child: TextField(
          key: Key(key),
          controller: c,
          maxLength: max,
          autocorrect: false,
          keyboardType: keyboard,
          autofillHints: hints,
          decoration: InputDecoration(labelText: label, counterText: ''),
          onChanged: (_) => setState(() {}),
        ),
      );
}
