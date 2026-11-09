import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/tokens.dart';
import '../util/app_time.dart';
import '../widgets/profile_kit.dart';
import 'save_password_sheet.dart';
import 'vault_models.dart';
import 'vault_repo.dart';

const vaultPasswordsNote =
    'Roost keeps these sealed. Your bots never see them; Roost types one only after your Yes, '
    'or at once on a site you set to Always.';
const _emptyText = 'No saved passwords. Add one here, or tick Save in Vault on a Sign-in card.';

/// "ana@example.com · Last used Sat 7 Nov, 09:30".
String savedLoginLine(SavedLogin login) {
  final used = login.lastUsedAt;
  final when = used == null || used.isEmpty ? 'Not used yet' : 'Last used ${appDayClock(used)}';
  return login.username.isEmpty ? when : '${login.username} · $when';
}

/// Vault: passwords (owner, 2026-11-08), from Settings: each saved login's
/// site, user name and last use (never its password), Always for this site,
/// Delete, and Add.
class VaultPasswordsScreen extends ConsumerWidget {
  const VaultPasswordsScreen({super.key});

  Future<void> _add(BuildContext context, WidgetRef ref) async {
    if (await showSavePasswordSheet(context)) ref.invalidate(vaultPasswordsProvider);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final logins = ref.watch(vaultPasswordsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Vault: passwords'), actions: [
        IconButton(
          key: const Key('vault-add'),
          tooltip: 'Add',
          icon: const Icon(Icons.add),
          onPressed: () => _add(context, ref),
        ),
      ]),
      body: ListView(
        padding: const EdgeInsets.symmetric(vertical: Tokens.space2),
        children: [
          ...logins.when(
            data: (rows) => rows.isEmpty
                ? [const _Pad(Quiet(_emptyText))]
                : [for (final login in rows) _LoginRow(login: login)],
            error: (e, _) => [
              _Pad(Quiet(describe(e), bad: true)),
              TextButton(
                  onPressed: () => ref.invalidate(vaultPasswordsProvider),
                  child: const Text('Try again')),
            ],
            loading: () => const [Center(child: CircularProgressIndicator())],
          ),
          const SizedBox(height: Tokens.space2),
          const _Pad(Quiet(vaultPasswordsNote)),
        ],
      ),
    );
  }
}

const _rowPadding = EdgeInsets.symmetric(horizontal: Tokens.space3);

class _Pad extends StatelessWidget {
  const _Pad(this.child);

  final Widget child;

  @override
  Widget build(BuildContext context) =>
      Padding(padding: const EdgeInsets.symmetric(horizontal: Tokens.space4), child: child);
}

class _LoginRow extends ConsumerWidget {
  const _LoginRow({required this.login});

  final SavedLogin login;

  Future<void> _always(BuildContext context, WidgetRef ref, bool on) async {
    final ok = await attempt(context, () => ref.read(vaultPasswordsRepoProvider).setAlways(login.id, on));
    if (ok) ref.invalidate(vaultPasswordsProvider);
  }

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    if (!await confirm(context, 'Delete the ${login.host} login?', 'Delete',
        body: 'Roost forgets this password. Your bots will ask you to sign in again.')) {
      return;
    }
    if (!context.mounted) return;
    final ok = await attempt(context, () => ref.read(vaultPasswordsRepoProvider).delete(login.id));
    if (ok) ref.invalidate(vaultPasswordsProvider);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) => InfoCard(children: [
        ListTile(
          contentPadding: _rowPadding,
          title: Text(login.host),
          subtitle: Text(savedLoginLine(login),
              style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          trailing: TextButton(
            key: Key('vault-delete-${login.id}'),
            onPressed: () => _delete(context, ref),
            child: const Text('Delete', style: TextStyle(color: Tokens.dangerText)),
          ),
        ),
        SwitchListTile(
          key: Key('vault-always-${login.id}'),
          contentPadding: _rowPadding,
          title: const Text('Always for this site'),
          value: login.always,
          onChanged: (on) => _always(context, ref, on),
        ),
      ]);
}
