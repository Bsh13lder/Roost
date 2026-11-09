import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import 'plan_models.dart';

/// A bot's Plan over HTTP (roost/gateway/routes/plan.py). Every save carries
/// the revision it read; a stale one is a 409 holding the current copy.
class PlanRepo {
  PlanRepo(this._ref, this.botId);

  final Ref _ref;
  final String botId;

  String get _path => '/api/bots/${Uri.encodeComponent(botId)}/plan';

  PlanData _data(Object? json) =>
      PlanData.fromJson((json as Map).cast<String, dynamic>());

  Future<PlanData> read() async =>
      _data(await _ref.read(apiClientProvider).get(_path));

  Future<PlanData> putText(String content, int baseRevision) async => _data(
      await _ref.read(apiClientProvider).put(
          _path, {'content': content, 'base_revision': baseRevision}));

  Future<PlanData> moveItem(String itemId, int baseRevision, String status) async =>
      _data(await _ref.read(apiClientProvider).patch(
          '$_path/items/${Uri.encodeComponent(itemId)}',
          {'base_revision': baseRevision, 'status': status}));
}

final planRepoProvider =
    Provider.family<PlanRepo, String>((ref, botId) => PlanRepo(ref, botId));
