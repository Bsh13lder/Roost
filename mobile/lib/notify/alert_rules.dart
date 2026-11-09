import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../api/models.dart' show Avatar;
import '../util/app_time.dart';
import 'notify_prefs.dart';

typedef Frame = Map<String, dynamic>;

/// The longest title and body line a notification shows.
const alertTitleMax = 60;
const alertBodyMax = 120;

/// How many alert keys are remembered so a resumed socket never repeats one.
const seenKeysMax = 500;

/// How much of a streamed reply is kept for its notification.
const replyBufferMax = 400;

enum AlertKind { needsOk, report, reply, reminder }

/// What the app shows right now: alerts about the open chat are never sent,
/// and replies only alert while the app is away.
@immutable
class AppFocus {
  const AppFocus({required this.visible, this.openChatBotId});

  static const away = AppFocus(visible: false);

  final bool visible;
  final String? openChatBotId;

  Map<String, Object?> toJson() => {'visible': visible, 'chat': openChatBotId};

  factory AppFocus.fromJson(Object? raw) => raw is Map && raw['visible'] == true
      ? AppFocus(visible: true, openChatBotId: raw['chat'] as String?)
      : away;
}

/// A stable positive id for a notification, so the same alert replaces itself.
int alertIdFor(String key) {
  var h = 0x811c9dc5;
  for (final unit in key.codeUnits) {
    h = ((h ^ unit) * 0x01000193) & 0x7fffffff;
  }
  return h == 0 ? 1 : h;
}

@immutable
class Alert {
  const Alert({
    required this.key,
    required this.kind,
    required this.botId,
    required this.title,
    required this.body,
    this.avatar,
  });

  /// What it is about (`card:<id>`, `msg:<id>`): one alert per key.
  final String key;
  final AlertKind kind;
  final String botId;
  final String title;
  final String body;

  /// The bot's look, for its face on the notification (null: no face).
  final Avatar? avatar;

  int get id => alertIdFor(key);

  Alert withAvatar(Avatar? look) =>
      Alert(key: key, kind: kind, botId: botId, title: title, body: body, avatar: look);
}

/// The bot's name and its own Notifications switch.
@immutable
class _BotBrief {
  const _BotBrief(this.name, this.notify, this.avatar);
  final String name;
  final bool notify;
  final Avatar? avatar;
}

/// Reads `/api/events` frames and decides which become a notification.
/// It holds only names, open streams and the keys it has alerted on; never a
/// whole chat.
class AlertBook {
  Map<String, _BotBrief> _bots = const {};
  final Map<String, String> _streamBot = {};
  final Map<String, String> _streamText = {};
  final Map<String, bool> _streamTaint = {};

  /// Routine run logs seen so far (a `routine` line opens every run): a run's
  /// own replies there never alert; its Report in the bot's chat does
  /// (owner, 2026-11-05: "empty routine runs, so noisy").
  final Set<String> _routineThreads = {};
  final List<String> _seenOrder = [];
  final Set<String> _seen = {};

  Alert? take(Frame frame,
      {required NotifyPrefs prefs, required AppFocus focus, required DateTime now}) {
    final alert = _read(frame);
    if (alert == null || _seen.contains(alert.key)) return null;
    if (!_allowed(alert, prefs, focus, now)) return null;
    _remember(alert.key);
    return alert.withAvatar(_bots[alert.botId]?.avatar);
  }

  bool _allowed(Alert a, NotifyPrefs prefs, AppFocus focus, DateTime now) {
    if (!(_bots[a.botId]?.notify ?? true)) return false;
    final on = switch (a.kind) {
      AlertKind.needsOk => prefs.needsOk,
      AlertKind.report => prefs.reports,
      AlertKind.reply => prefs.replies,
      AlertKind.reminder => prefs.reminders,
    };
    if (!on) return false;
    if (focus.visible && (focus.openChatBotId == a.botId || a.kind == AlertKind.reply)) return false;
    // Quiet hours hush everything but the reminders you set yourself.
    return a.kind == AlertKind.reminder || !prefs.isQuietAt(appMinuteOfDay(now));
  }

  void _remember(String key) {
    _seen.add(key);
    _seenOrder.add(key);
    if (_seenOrder.length > seenKeysMax) _seen.remove(_seenOrder.removeAt(0));
  }

  Alert? _read(Frame frame) {
    switch (frame['type']) {
      case 'snapshot':
        _bots = {
          for (final b in (frame['bots'] as List? ?? const []))
            if (b is Map && b['id'] is String) b['id'] as String: _brief(b),
        };
      case 'bot_updated':
        final b = frame['bot'];
        if (b is Map && b['id'] is String) _bots = {..._bots, b['id'] as String: _brief(b)};
      case 'bot_removed':
        _bots = {..._bots}..remove(frame['bot_id']);
      case 'message':
        final m = frame['message'];
        if (m is Map) return _fromMessage(m.cast<String, dynamic>());
      case 'text_delta':
        final id = frame['message_id'];
        final delta = frame['delta'];
        if (id is String && delta is String && _streamBot.containsKey(id)) {
          final text = (_streamText[id] ?? '') + delta;
          _streamText[id] = text.length > replyBufferMax ? text.substring(0, replyBufferMax) : text;
        }
      case 'message_done':
        return _finished(frame['message_id']);
    }
    return null;
  }

  static _BotBrief _brief(Map b) => _BotBrief(
      '${b['name'] ?? ''}', b['notify'] != false, b['avatar'] is Map ? Avatar.fromJson(b['avatar']) : null);

  String _name(String botId) {
    final name = _bots[botId]?.name ?? '';
    return name.isEmpty ? 'A bot' : name;
  }

  Alert? _finished(Object? id) {
    if (id is! String) return null;
    final botId = _streamBot.remove(id);
    final text = _streamText.remove(id) ?? '';
    final tainted = _streamTaint.remove(id) ?? false;
    if (botId == null || text.trim().isEmpty) return null;
    return _alert('msg:$id', AlertKind.reply, botId, _name(botId), text, tainted: tainted);
  }

  Alert? _fromMessage(Map<String, dynamic> m) {
    if (m['kind'] == 'routine' && m['thread_id'] is String) _routineThreads.add(m['thread_id'] as String);
    final botId = m['author_bot_id'];
    final id = m['id'];
    if (botId is! String || id is! String || m['role'] != 'bot') return null;
    final kind = m['kind'] as String? ?? 'text';
    final body = '${m['body'] ?? ''}';
    final tainted = m['tainted'] == true;
    final name = _name(botId);
    if (kind == 'text' && _routineThreads.contains(m['thread_id'])) return null;
    if (kind == 'text') {
      if (body.isEmpty) {
        _streamBot[id] = botId;
        _streamTaint[id] = tainted;
        return null;
      }
      return _alert('msg:$id', AlertKind.reply, botId, name, body, tainted: tainted);
    }
    final json = _json(body);
    return switch (kind) {
      'approval' => _approval(json, botId, name),
      'stuck' => _stuck(json, botId, name),
      'report' => _report(json, id, botId, name, tainted),
      'routine_proposal' => _needs('msg:$id', botId, name, 'A routine to approve'),
      'skill_proposal' => _needs('msg:$id', botId, name, 'A skill to save: ${json['name'] ?? ''}'.trim()),
      'instructions_proposal' => _needs('msg:$id', botId, name, 'A change to its instructions'),
      'connector_request' => _needs('msg:$id', botId, name, 'A key for ${json['service'] ?? 'a service'}'),
      _ => null,
    };
  }

  Alert? _approval(Map<String, dynamic> j, String botId, String name) {
    final cardId = j['card_id'];
    if (cardId is! String) return null;
    final steps = [for (final s in (j['steps'] as List? ?? const [])) '$s'];
    final line = j['kind'] == 'plan' || steps.length > 1
        ? '${steps.length} changes to review'
        : (steps.isEmpty ? 'Tap to answer' : steps.first);
    return _alert('card:$cardId', AlertKind.needsOk, botId, '$name needs your OK', line);
  }

  Alert? _stuck(Map<String, dynamic> j, String botId, String name) {
    final cardId = j['card_id'];
    if (cardId is! String) return null;
    final line = j['sign_in'] == true ? 'Sign in to ${j['host'] ?? 'a site'}' : '${j['line'] ?? 'It is stuck.'}';
    return _alert('card:$cardId', AlertKind.needsOk, botId, '$name needs you', line);
  }

  Alert? _report(Map<String, dynamic> j, String id, String botId, String name, bool tainted) {
    final headline = '${j['headline'] ?? ''}';
    final text = '${j['text'] ?? ''}';
    if (j['source'] == 'reminder') {
      return _alert('msg:$id', AlertKind.reminder, botId, headline.isEmpty ? 'Reminder' : headline, text);
    }
    return _alert('msg:$id', AlertKind.report, botId, '$name: $headline', text, tainted: tainted);
  }

  Alert _needs(String key, String botId, String name, String line) =>
      _alert(key, AlertKind.needsOk, botId, '$name needs your OK', line);

  static Alert _alert(String key, AlertKind kind, String botId, String title, String text,
          {bool tainted = false}) =>
      Alert(
        key: key,
        kind: kind,
        botId: botId,
        title: _clip(title, alertTitleMax),
        body: _clip(_firstLine(text), alertBodyMax),
      );

  static String _firstLine(String text) =>
      text.split('\n').map((l) => l.trim()).firstWhere((l) => l.isNotEmpty, orElse: () => '');

  static String _clip(String text, int max) =>
      text.length <= max ? text : '${text.substring(0, max - 1).trimRight()}…';

  static Map<String, dynamic> _json(String body) {
    try {
      final v = jsonDecode(body);
      return v is Map ? v.cast<String, dynamic>() : const {};
    } on FormatException {
      return const {};
    }
  }
}
