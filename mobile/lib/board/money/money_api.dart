import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/providers.dart';
import '../common/raw_request.dart';

typedef Json = Map<String, dynamic>;

/// The Money tab's routes. Every amount stays the string the server sent.
class MoneyApi {
  const MoneyApi(this._c);

  final ApiClient _c;

  Future<Json> range(String from, String to, {String? projectId}) async {
    final p = projectId == null
        ? ''
        : '&project_id=${Uri.encodeComponent(projectId)}';
    return Map<String, dynamic>.from(
        await _c.get('/api/money/range?from=$from&to=$to$p') as Map);
  }

  Future<Json> summary(String month) async => Map<String, dynamic>.from(
      await _c.get('/api/money/summary?month=$month') as Map);

  Future<Json> parse(String text,
      {String? projectId, List<String> skip = const []}) async {
    final r = await _c.post('/api/money/parse', {
      'text': text,
      'project_id': ?projectId,
      if (skip.isNotEmpty) 'skip': skip,
    });
    return Map<String, dynamic>.from(r as Map);
  }

  Future<Json> create(Json body) async => Map<String, dynamic>.from(
      await _c.post('/api/money/expenses', body) as Map);

  Future<Json> patch(String id, Json patch) async => Map<String, dynamic>.from(
      await rawRequest(_c, 'PATCH',
          '/api/money/expenses/${Uri.encodeComponent(id)}', patch) as Map);

  Future<void> delete(String id) =>
      _c.delete('/api/money/expenses/${Uri.encodeComponent(id)}');

  Future<void> restore(String id) =>
      _c.post('/api/money/expenses/${Uri.encodeComponent(id)}/restore');

  Future<void> star(String id, bool starred) => _c.put(
      '/api/money/expenses/${Uri.encodeComponent(id)}/star',
      {'starred': starred});

  Future<void> voidIt(String id, bool isVoid) => _c.put(
      '/api/money/expenses/${Uri.encodeComponent(id)}/void', {'void': isVoid});
}

final moneyApiProvider =
    Provider<MoneyApi>((ref) => MoneyApi(ref.watch(apiClientProvider)));
