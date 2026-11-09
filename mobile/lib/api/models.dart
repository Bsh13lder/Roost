import 'package:flutter/material.dart';

import '../voice/voice_models.dart';
import '../media/media_ref.dart';

export '../voice/voice_models.dart' show BotVoice;

/// Bot statuses (CLAUDE.md vocabulary: Resting · On it · Asking you · Stuck · Off duty).
enum BotStatus { resting, onIt, askingYou, stuck, offDuty }

BotStatus _status(Object? raw) => switch (raw) {
      'on_it' => BotStatus.onIt,
      'asking_you' => BotStatus.askingYou,
      'stuck' => BotStatus.stuck,
      'off_duty' => BotStatus.offDuty,
      _ => BotStatus.resting,
    };

String statusLabel(BotStatus s) => switch (s) {
      BotStatus.resting => 'Resting',
      BotStatus.onIt => 'On it',
      BotStatus.askingYou => 'Asking you',
      BotStatus.stuck => 'Stuck',
      BotStatus.offDuty => 'Off duty',
    };

@immutable
class Avatar {
  const Avatar({
    this.shape = 'mochi',
    this.color = '#6C5CE0',
    this.badge = 'none',
    this.screen,
    this.role,
    this.picture,
  });

  factory Avatar.fromJson(Object? json) {
    if (json is! Map) return const Avatar();
    return Avatar(
      shape: json['shape'] as String? ?? 'mochi',
      color: json['color'] as String? ?? '#6C5CE0',
      badge: json['badge'] as String? ?? 'none',
      screen: json['screen'] as String?,
      role: json['role'] as String?,
      picture: json['picture'] as String?,
    );
  }

  final String shape;
  final String color;
  final String badge;
  final String? screen;
  final String? role;

  /// Where the gateway serves the bot's own picture, when it has one.
  final String? picture;

  Avatar copyWith({String? shape, String? color, String? role}) => Avatar(
        shape: shape ?? this.shape,
        color: color ?? this.color,
        badge: badge,
        screen: screen,
        role: role ?? this.role,
        picture: picture,
      );

  /// What an edit sends (never the picture's address).
  Map<String, Object?> toJson() => {
        'shape': shape,
        'color': color,
        'badge': badge,
        'screen': screen ?? 'glow',
        if (role != null && role != 'general') 'role': role,
      };

  Color get colour {
    final hex = color.replaceFirst('#', '');
    final value = int.tryParse(hex, radix: 16);
    if (hex.length != 6 || value == null) return const Color(0xFF6C5CE0);
    return Color(0xFF000000 | value);
  }
}

@immutable
class Bot {
  const Bot({
    required this.id,
    required this.name,
    required this.avatar,
    required this.status,
    this.activity,
    this.group,
    this.isPrimary = false,
    this.pinned = false,
    this.pinnedAt,
    this.voice = const BotVoice(),
  });

  factory Bot.fromJson(Map<String, dynamic> j) => Bot(
        id: j['id'] as String,
        name: j['name'] as String? ?? '',
        avatar: Avatar.fromJson(j['avatar']),
        status: _status(j['status']),
        activity: j['activity'] as String?,
        group: (j['group'] as String?)?.trim(),
        isPrimary: j['is_primary'] == true,
        pinned: j['pinned'] == true,
        pinnedAt: j['pinned_at'] as String?,
        voice: BotVoice.fromJson(j['voice']),
      );

  final String id;
  final String name;
  final Avatar avatar;
  final BotStatus status;
  final String? activity;
  final String? group;
  final bool isPrimary;
  final bool pinned;
  final String? pinnedAt;

  /// Its voice, tone, speed and Read replies aloud (defaults when missing).
  final BotVoice voice;

  Bot withStatus(BotStatus s, String? a) => Bot(
        id: id,
        name: name,
        avatar: avatar,
        status: s,
        activity: a,
        group: group,
        isPrimary: isPrimary,
        pinned: pinned,
        pinnedAt: pinnedAt,
        voice: voice,
      );
}

@immutable
class ChatRow {
  const ChatRow({
    required this.kind,
    required this.id,
    required this.name,
    this.threadId,
    this.preview,
    this.previewKind,
    this.fromYou = false,
    this.lastAt = '',
  });

  factory ChatRow.fromJson(Map<String, dynamic> j) => ChatRow(
        kind: j['kind'] as String? ?? 'bot',
        id: j['id'] as String,
        name: j['name'] as String? ?? '',
        threadId: j['thread_id'] as String?,
        preview: j['preview'] as String?,
        previewKind: j['preview_kind'] as String?,
        fromYou: j['from_you'] == true,
        lastAt: j['last_at'] as String? ?? '',
      );

  final String kind;
  final String id;
  final String name;
  final String? threadId;
  final String? preview;
  final String? previewKind;
  final bool fromYou;
  final String lastAt;

  bool get isBot => kind == 'bot';

  ChatRow withName(String value) => ChatRow(
        kind: kind,
        id: id,
        name: value,
        threadId: threadId,
        preview: preview,
        previewKind: previewKind,
        fromYou: fromYou,
        lastAt: lastAt,
      );
}

@immutable
class Message {
  const Message({
    required this.id,
    required this.threadId,
    required this.role,
    required this.body,
    required this.seq,
    required this.createdAt,
    required this.kind,
    this.authorBotId,
    this.tainted = false,
    this.replyQuote,
    this.replyTainted = false,
    this.media = const [],
  });

  factory Message.fromJson(Map<String, dynamic> j) => Message(
        id: j['id'] as String,
        threadId: j['thread_id'] as String? ?? '',
        role: j['role'] as String? ?? 'bot',
        body: j['body'] as String? ?? '',
        seq: (j['seq'] as num?)?.toInt() ?? 0,
        createdAt: j['created_at'] as String? ?? '',
        kind: j['kind'] as String? ?? 'text',
        authorBotId: j['author_bot_id'] as String?,
        tainted: j['tainted'] == true,
        replyQuote: j['reply_quote'] as String?,
        replyTainted: j['reply_tainted'] == true,
        media: parseMedia(j['media']),
      );

  final String id;
  final String threadId;
  final String role;
  final String body;
  final int seq;
  final String createdAt;
  final String kind;
  final String? authorBotId;
  final bool tainted;

  /// The server's quote of the message this one answers.
  final String? replyQuote;
  final bool replyTainted;

  /// Its pictures: yours, a video's frames, or the bot's screenshots.
  final List<MediaRef> media;

  bool get isPlaceholder => seq == 0 && role == 'bot';
  bool get fromUser => role == 'user';
}

/// The reply to POST /api/threads/{id}/messages.
enum SendStatus { started, queued, steered }

SendStatus parseSendStatus(Object? raw) => switch (raw) {
      'queued' => SendStatus.queued,
      'steered' => SendStatus.steered,
      _ => SendStatus.started,
    };
