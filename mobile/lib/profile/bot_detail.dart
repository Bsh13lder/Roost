import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../api/providers.dart';
import '../live/bot_frames.dart';
import '../live/live_connection.dart';

/// The fields of `GET /api/bots/{id}` the Profile reads.
@immutable
class BotDetail {
  const BotDetail({
    required this.id,
    required this.name,
    required this.job,
    required this.instructions,
    required this.avatar,
    required this.model,
    required this.modelLabel,
    required this.effort,
    required this.notify,
    required this.isPrimary,
    required this.group,
    required this.computer,
    required this.approvalMode,
    required this.askTopics,
    required this.lockedTopics,
    required this.status,
    this.autoReview = false,
    this.fullLimitUntil,
    this.voice = const BotVoice(),
  });

  factory BotDetail.fromJson(Map<String, dynamic> j) {
    final approval = (j['approval'] as Map?)?.cast<String, dynamic>() ?? {};
    List<String> list(Object? v) =>
        [for (final x in (v as List? ?? const [])) x as String];
    return BotDetail(
      id: j['id'] as String,
      name: j['name'] as String? ?? '',
      job: j['job'] as String? ?? '',
      instructions: j['instructions'] as String? ?? '',
      avatar: Avatar.fromJson(j['avatar']),
      model: j['model'] as String? ?? '',
      modelLabel: j['model_label'] as String? ?? '',
      effort: j['effort'] as String?,
      notify: j['notify'] == true,
      isPrimary: j['is_primary'] == true,
      group: (j['group'] as String?)?.trim() ?? '',
      computer: j['computer'] as String? ?? 'mac',
      approvalMode: approval['mode'] as String? ?? 'ask',
      askTopics: list(approval['ask_topics']),
      lockedTopics: list(approval['locked_topics']),
      autoReview: approval['auto_review'] == true,
      status: switch (j['status']) {
        'on_it' => BotStatus.onIt,
        'asking_you' => BotStatus.askingYou,
        'stuck' => BotStatus.stuck,
        'off_duty' => BotStatus.offDuty,
        _ => BotStatus.resting,
      },
      fullLimitUntil: j['full_limit_until'] as String?,
      voice: BotVoice.fromJson(j['voice']),
    );
  }

  final String id, name, job, instructions, model, modelLabel, group, computer;
  final String approvalMode;
  final Avatar avatar;
  final String? effort;
  final bool notify, isPrimary;
  final List<String> askTopics, lockedTopics;
  final BotStatus status;

  /// The checker looks at buttons the bot can't read (Full auto).
  final bool autoReview;

  /// Set while "Use the full limit until it resets" is on.
  final String? fullLimitUntil;

  /// Its voice, tone, speed and Read replies aloud.
  final BotVoice voice;
}

/// One bot's detail; every save puts the server's answer back with [replace],
/// and a `bot_updated` frame for this bot (a change made elsewhere: the web,
/// the bot's own set_my_voice) fetches it again, so Settings and a call in
/// progress see the new values.
class BotDetailNotifier extends FamilyAsyncNotifier<BotDetail, String> {
  StreamSubscription<Frame>? _sub;

  @override
  Future<BotDetail> build(String arg) async {
    ref.onDispose(() {
      _sub?.cancel();
      _sub = null;
    });
    _sub ??= ref.read(frameBusProvider).stream.listen(_onFrame);
    return _fetch(arg);
  }

  Future<BotDetail> _fetch(String botId) async {
    final data = await ref.read(apiClientProvider).get('/api/bots/$botId');
    return BotDetail.fromJson((data as Map).cast<String, dynamic>());
  }

  void _onFrame(Frame frame) {
    if (frame['type'] != 'bot_updated') return;
    final bot = frame['bot'];
    if (bot is! Map || bot['id'] != arg) return;
    unawaited(_refresh());
  }

  /// The fresh copy replaces the shown one; a failed fetch keeps what shows.
  Future<void> _refresh() async {
    try {
      state = AsyncData(await _fetch(arg));
    } catch (_) {
      // The next frame or save tries again; the old copy stays on screen.
    }
  }

  void replace(Object? json) {
    if (json is Map) {
      state = AsyncData(BotDetail.fromJson(json.cast<String, dynamic>()));
    }
  }
}

/// `PUT /api/bots/{id}/approval`; [autoReview] is sent only when given, so
/// leaving it out keeps the stored value. The bot it returns replaces the
/// local one.
Future<void> saveApproval(WidgetRef ref, String botId,
    {required String mode,
    required List<String> topics,
    bool? autoReview}) async {
  final saved = await ref.read(apiClientProvider).put('/api/bots/$botId/approval', {
    'mode': mode,
    'ask_topics': topics,
    'auto_review': ?autoReview,
  });
  ref.read(botDetailProvider(botId).notifier).replace(saved);
}

final botDetailProvider =
    AsyncNotifierProvider.family<BotDetailNotifier, BotDetail, String>(
        BotDetailNotifier.new);
