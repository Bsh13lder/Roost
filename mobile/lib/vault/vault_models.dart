/// One saved login in Vault: passwords (owner, 2026-11-08). The server never
/// sends a password, so there is no field for one here.
class SavedLogin {
  const SavedLogin({
    required this.id,
    required this.host,
    required this.username,
    required this.always,
    required this.createdAt,
    required this.updatedAt,
    this.lastUsedAt,
  });

  final String id;
  final String host;
  final String username;

  /// Your standing OK: Roost types it on this site with no Ask card.
  final bool always;
  final String createdAt;
  final String updatedAt;
  final String? lastUsedAt;

  factory SavedLogin.fromJson(Map<String, dynamic> json) => SavedLogin(
        id: json['id'] as String,
        host: json['host'] as String? ?? '',
        username: json['username'] as String? ?? '',
        always: json['always'] == true,
        createdAt: json['created_at'] as String? ?? '',
        updatedAt: json['updated_at'] as String? ?? '',
        lastUsedAt: json['last_used_at'] as String?,
      );

  SavedLogin copyWith({bool? always}) => SavedLogin(
        id: id,
        host: host,
        username: username,
        always: always ?? this.always,
        createdAt: createdAt,
        updatedAt: updatedAt,
        lastUsedAt: lastUsedAt,
      );

  @override
  String toString() => 'SavedLogin($id, $host)';
}

/// What Save a password sends: the one place a password is held, briefly.
class NewLogin {
  const NewLogin({required this.host, required this.username, required this.password});

  final String host;
  final String username;
  final String password;

  Map<String, dynamic> toJson() =>
      {'host': host, 'username': username, 'password': password};

  @override
  String toString() => 'NewLogin($host)';
}
