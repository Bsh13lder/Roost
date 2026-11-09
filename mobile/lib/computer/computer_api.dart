import '../api/api_client.dart';

typedef Json = Map<String, dynamic>;

const accountMaxChars = 100; // SITE_LOGIN_LABEL_MAX_CHARS
const teachDescriptionMax = 200; // TEACH_DESCRIPTION_MAX

const controlGivenBackText = 'Control was given back.';
const teachProposedText = 'The skill is in the chat. Press Save skill to keep it.';
const teachDiscardedText = 'The recording was thrown away.';

/// A bot's open Stuck card, when it has one (I'm done clears it).
class OpenStuck {
  const OpenStuck({required this.id, required this.host, required this.signIn});
  final String id, host;
  final bool signIn;
}

/// The routes the web's `api/computer.ts`, `api/teach.ts` and `api/stuck.ts`
/// use for Take control, Teach and I'm done.
class ComputerApi {
  const ComputerApi(this._api);
  final ApiClient _api;

  Future<bool> held(String botId) async =>
      _held(await _api.get('/api/bots/$botId/control'));

  Future<bool> takeControl(String botId) async =>
      _held(await _api.post('/api/bots/$botId/control'));

  bool _held(Object? v) => v is Map && v['held'] == true;

  /// Give it back; the account label goes along only when given.
  Future<void> giveBack(String botId, {String? account}) => _api.delete(
      '/api/bots/$botId/control',
      account == null || account.isEmpty ? null : {'account': account});

  Future<void> wake(String botId) =>
      _api.post('/api/bots/$botId/desk/browser/start');

  Future<bool> teaching(String botId) async {
    final v = await _api.get('/api/bots/$botId/teach');
    return v is Map && v['teaching'] == true;
  }

  Future<bool> startTeach(String botId) async {
    final v = await _api.post('/api/bots/$botId/teach/start');
    return v is Map && v['teaching'] == true;
  }

  /// Returns true when the recording was thrown away.
  Future<bool> stopTeach(String botId,
      {String? description, bool discard = false}) async {
    final body = <String, dynamic>{
      if (discard) 'discard': true,
      if (!discard && description != null && description.isNotEmpty)
        'description': description,
    };
    final v = await _api.post('/api/bots/$botId/teach/stop', body);
    return v is Map && v['discarded'] == true;
  }

  Future<OpenStuck?> openStuck(String botId) async {
    final list = await _api.get('/api/stuck');
    if (list is! List) return null;
    for (final c in list) {
      if (c is Map && c['bot_id'] == botId && c['state'] == 'open') {
        return OpenStuck(
          id: '${c['id']}',
          host: c['host'] is String ? c['host'] as String : '',
          signIn: c['sign_in'] == true,
        );
      }
    }
    return null;
  }

  /// I'm done with a Stuck card: clear it with the account and, on a
  /// Sign-in card, `keep`. Only the fields given go along.
  Future<void> clearStuck(String cardId, {String? account, bool? keep}) {
    final body = <String, dynamic>{
      if (account != null && account.isNotEmpty) 'account': account,
      'keep': ?keep,
    };
    return _api.post('/api/stuck/$cardId/clear', body.isEmpty ? null : body);
  }
}
