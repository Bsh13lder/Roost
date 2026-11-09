/// One picture on a chat message (owner, 2026-11-05: pictures and video in
/// the chat): yours or the bot's, a frame of a video when [video].
class MediaRef {
  const MediaRef({
    required this.id,
    required this.width,
    required this.height,
    required this.fromBot,
    required this.video,
  });

  factory MediaRef.fromJson(Map<String, dynamic> j) => MediaRef(
        id: j['id'] as String,
        width: (j['width'] as num?)?.toInt() ?? 0,
        height: (j['height'] as num?)?.toInt() ?? 0,
        fromBot: j['source'] == 'bot',
        video: j['group'] == 'video',
      );

  final String id;
  final int width, height;
  final bool fromBot, video;

  String get path => '/api/media/${Uri.encodeComponent(id)}';
}

List<MediaRef> parseMedia(Object? raw) => [
      for (final m in (raw as List? ?? const []))
        if (m is Map && m['id'] is String) MediaRef.fromJson(m.cast<String, dynamic>()),
    ];

/// A run of photos, or of one video's frames, in the message's order.
class MediaGroup {
  const MediaGroup(this.video, this.items);
  final bool video;
  final List<MediaRef> items;
}

List<MediaGroup> mediaGroups(List<MediaRef> media) {
  final groups = <MediaGroup>[];
  for (final m in media) {
    if (groups.isNotEmpty && groups.last.video == m.video) {
      groups.last.items.add(m);
    } else {
      groups.add(MediaGroup(m.video, [m]));
    }
  }
  return groups;
}

String videoLabel(int frames) => 'Video · $frames frames';
