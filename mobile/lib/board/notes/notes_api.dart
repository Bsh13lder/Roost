import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/providers.dart';
import '../common/raw_request.dart';

typedef Json = Map<String, dynamic>;

/// The Notes routes. A save with a stale revision throws [RevisionConflict].
class NotesApi {
  const NotesApi(this._c);

  final ApiClient _c;

  static String _path(String id) => '/api/notes/${Uri.encodeComponent(id)}';

  Future<List<Json>> list({String query = '', String? projectId}) async {
    final params = [
      if (query.trim().isNotEmpty) 'q=${Uri.encodeComponent(query.trim())}',
      if (projectId != null) 'project_id=${Uri.encodeComponent(projectId)}',
    ];
    final r = await _c.get(
        params.isEmpty ? '/api/notes' : '/api/notes?${params.join('&')}');
    return [for (final n in (r as List)) Map<String, dynamic>.from(n as Map)];
  }

  Future<Json> get(String id) async =>
      Map<String, dynamic>.from(await _c.get(_path(id)) as Map);

  Future<Json> create({String? title, required String content, String? projectId}) async =>
      Map<String, dynamic>.from(await _c.post('/api/notes', {
        if (title != null && title.isNotEmpty) 'title': title,
        'content': content,
        'project_id': ?projectId,
      }) as Map);

  Future<Json> save(String id,
          {required int baseRevision, String? title, String? content}) async =>
      Map<String, dynamic>.from(await rawRequest(_c, 'PUT', _path(id), {
        'base_revision': baseRevision,
        'title': ?title,
        'content': ?content,
      }) as Map);

  Future<void> delete(String id) => _c.delete(_path(id));
}

final notesApiProvider =
    Provider<NotesApi>((ref) => NotesApi(ref.watch(apiClientProvider)));
