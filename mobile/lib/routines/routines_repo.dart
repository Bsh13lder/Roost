import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/providers.dart';

typedef Json = Map<String, dynamic>;

List<Json> _rows(Object? v) =>
    [for (final x in (v as List? ?? const [])) (x as Map).cast<String, dynamic>()];

/// Routines over HTTP (roost/gateway/routes/routines.py, routines_hub.py).
class RoutinesRepo {
  RoutinesRepo(this._api);

  final ApiClient _api;

  static String _routine(String id) => '/api/routines/${Uri.encodeComponent(id)}';
  static String _bot(String id) => '/api/bots/${Uri.encodeComponent(id)}';

  Future<List<Json>> all() async =>
      _rows(((await _api.get('/api/routines')) as Map)['routines']);

  Future<List<Json>> recentRuns([int limit = 20]) async => _rows(
      ((await _api.get('/api/routines/runs?limit=$limit')) as Map)['runs']);

  Future<List<Json>> templates() async => _rows(
      ((await _api.get('/api/routine-templates')) as Map)['templates']);

  Future<List<Json>> forBot(String botId) async =>
      _rows(((await _api.get('${_bot(botId)}/routines')) as Map)['routines']);

  Future<List<Json>> runs(String routineId) async => _rows(
      ((await _api.get('${_routine(routineId)}/runs')) as Map)['runs']);

  Future<void> runNow(String id) => _api.post('${_routine(id)}/run-now');

  Future<void> setEnabled(String id, bool on) =>
      _api.patch(_routine(id), {'enabled': on});

  Future<void> create(String botId, Json draft) =>
      _api.post('${_bot(botId)}/routines', draft);

  Future<void> change(String id, Json draft) => _api.patch(_routine(id), draft);

  Future<void> delete(String id) => _api.delete(_routine(id));

  Future<void> addTemplate(String botId, String templateId) => _api.post(
      '${_bot(botId)}/routines/from-template', {'template_id': templateId});

  Future<Json> preview(Json schedule) async => ((await _api
          .post('/api/routines/preview', {'schedule': schedule})) as Map)
      .cast<String, dynamic>();

  /// Routine run times on the account's days [from]..[to] (`GET
  /// /api/routines/occurrences`), only [botId]'s when given.
  Future<List<Json>> occurrences(String from, String to, {String? botId}) async {
    final query = Uri(queryParameters: {
      'from': from,
      'to': to,
      'bot_id': ?botId,
    }).query;
    return _rows(((await _api.get('/api/routines/occurrences?$query')) as Map)['occurrences']);
  }

  Future<List<Json>> logMessages(String threadId) async {
    final data = await _api
        .get('/api/threads/${Uri.encodeComponent(threadId)}/messages');
    return _rows(data);
  }
}

final routinesRepoProvider =
    Provider<RoutinesRepo>((ref) => RoutinesRepo(ref.watch(apiClientProvider)));

const weekdayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

String runStateWords(String? state) => switch (state) {
      'done' => 'Done',
      'running' => 'Running',
      'queued' => 'Queued',
      'missed' => 'Missed',
      'skipped' => 'Skipped',
      'held' => 'Held',
      'expired' => 'Expired',
      'error' => 'Failed',
      _ => '',
    };
