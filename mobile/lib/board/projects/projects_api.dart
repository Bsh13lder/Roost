import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/providers.dart';

typedef Json = Map<String, dynamic>;

class ProjectsApi {
  const ProjectsApi(this._c);

  final ApiClient _c;

  /// General is never listed; pinned projects come first (the app only orders).
  Future<List<Json>> list() async {
    final r = await _c.get('/api/projects');
    final all = [for (final p in (r as List)) Map<String, dynamic>.from(p as Map)];
    return [
      ...all.where((p) => p['pinned'] == true),
      ...all.where((p) => p['pinned'] != true),
    ];
  }

  Future<Json> get(String id) async => Map<String, dynamic>.from(
      await _c.get('/api/projects/${Uri.encodeComponent(id)}') as Map);

  Future<void> update(String id, Json patch) =>
      _c.patch('/api/projects/${Uri.encodeComponent(id)}', patch);

  /// The total budget has its own call; null clears it.
  Future<void> setBudget(String id, String? amount) => _c
      .put('/api/projects/${Uri.encodeComponent(id)}/budget', {'amount': amount});

  Future<void> addTopup(String id, String amount, String? source) =>
      _c.post('/api/projects/${Uri.encodeComponent(id)}/topups',
          {'amount': amount, 'source': ?source});

  /// [amount] is the top-up's new amount.
  Future<void> editTopup(String topupId, String amount) => _c
      .patch('/api/topups/${Uri.encodeComponent(topupId)}', {'amount': amount});

  Future<void> undoTopup(String topupId) =>
      _c.post('/api/topups/${Uri.encodeComponent(topupId)}/undo');

  Future<void> pin(String id, bool pinned) => _c
      .put('/api/projects/${Uri.encodeComponent(id)}/pin', {'pinned': pinned});
}

final projectsApiProvider =
    Provider<ProjectsApi>((ref) => ProjectsApi(ref.watch(apiClientProvider)));
