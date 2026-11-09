import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/providers.dart';
import 'vault_models.dart';

const vaultPasswordsPath = '/api/vault/passwords';

/// Vault: passwords over the gateway (owner, 2026-11-08; the server's
/// roost/gateway/routes/vault_passwords.py). A password only ever goes out,
/// in [save]; no reply holds one.
class VaultPasswordsRepo {
  const VaultPasswordsRepo(this._api);

  final ApiClient _api;

  String _one(String id) => '$vaultPasswordsPath/${Uri.encodeComponent(id)}';

  Future<List<SavedLogin>> list() async {
    final data = await _api.get(vaultPasswordsPath);
    if (data is! List) return const [];
    return List.unmodifiable([
      for (final row in data)
        if (row is Map) SavedLogin.fromJson(row.cast<String, dynamic>()),
    ]);
  }

  Future<SavedLogin> save(NewLogin login) async => SavedLogin.fromJson(
      ((await _api.post(vaultPasswordsPath, login.toJson())) as Map).cast<String, dynamic>());

  Future<SavedLogin> setAlways(String id, bool always) async => SavedLogin.fromJson(
      ((await _api.patch(_one(id), {'always': always})) as Map).cast<String, dynamic>());

  Future<void> delete(String id) => _api.delete(_one(id));
}

final vaultPasswordsRepoProvider =
    Provider<VaultPasswordsRepo>((ref) => VaultPasswordsRepo(ref.watch(apiClientProvider)));

/// Your saved logins, newest from the server; invalidate after a change.
final vaultPasswordsProvider = FutureProvider.autoDispose<List<SavedLogin>>(
    (ref) => ref.watch(vaultPasswordsRepoProvider).list());
