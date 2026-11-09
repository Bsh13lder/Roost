/// An error shown to the user as-is: always a friendly sentence.
class ApiException implements Exception {
  const ApiException(this.message, {this.status, this.body});

  final String message;
  final int? status;

  /// The response body of a 409, which holds the stored copy as `current`.
  final Object? body;

  bool get isConflict => status == 409;

  /// The stored copy a 409 carries, if any.
  Map<String, dynamic>? get current {
    final b = body;
    final c = b is Map ? b['current'] : null;
    return c is Map ? c.cast<String, dynamic>() : null;
  }

  bool get isUnauthorized => status == 401;

  @override
  String toString() => message;
}
