import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/providers.dart';

typedef Json = Map<String, dynamic>;

class DocumentsApi {
  const DocumentsApi(this._c);

  final ApiClient _c;

  Future<List<Json>> list({String? projectId}) async {
    final r = await _c.get(projectId == null
        ? '/api/documents'
        : '/api/documents?project_id=${Uri.encodeComponent(projectId)}');
    return [for (final d in (r as List)) Map<String, dynamic>.from(d as Map)];
  }

  Future<Json> get(String id) async => Map<String, dynamic>.from(
      await _c.get('/api/documents/${Uri.encodeComponent(id)}') as Map);
}

final documentsApiProvider =
    Provider<DocumentsApi>((ref) => DocumentsApi(ref.watch(apiClientProvider)));
