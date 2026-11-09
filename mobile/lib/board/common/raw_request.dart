import 'package:dio/dio.dart';

import '../../api/api_client.dart';
import '../../api/api_error.dart';

/// A save that carried a stale revision: the gateway answers 409 with the
/// stored copy in `current`.
class RevisionConflict extends ApiException {
  const RevisionConflict(this.current)
      : super('This changed somewhere else since you opened it.', status: 409);

  @override
  final Map<String, dynamic> current;
}

/// For verbs [ApiClient] has no helper for (PATCH), and for calls whose error
/// body matters (409 with the current copy). Shares the client's headers.
Future<dynamic> rawRequest(
  ApiClient c,
  String method,
  String path, [
  Object? body,
]) async {
  try {
    final r = await c.dio
        .request<dynamic>(path, data: body, options: Options(method: method));
    return r.data;
  } on DioException catch (e) {
    final status = e.response?.statusCode;
    final data = e.response?.data;
    if (status == 401) {
      c.onUnauthorized();
      throw const ApiException('Please sign in again.', status: 401);
    }
    if (status == 409 && data is Map && data['current'] is Map) {
      throw RevisionConflict(Map<String, dynamic>.from(data['current'] as Map));
    }
    if (data is Map && data['detail'] is String) {
      throw ApiException(data['detail'] as String, status: status);
    }
    if (status == 404) throw const ApiException("That wasn't found.", status: 404);
    if (status != null && status >= 500) {
      throw ApiException('Roost had a problem. Try again.', status: status);
    }
    throw const ApiException(
        unreachableMessage);
  }
}
