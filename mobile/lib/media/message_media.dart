import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import '../theme/tokens.dart';
import 'media_ref.dart';

const _thumb = 96.0;
const _frameThumb = 56.0;

/// A picture's bytes from the gateway, with the app's own session.
final mediaBytesProvider = FutureProvider.family<Uint8List, String>(
    (ref, path) => ref.read(apiClientProvider).getBytes(path));

/// A message's pictures: photos in a small grid, a video's frames as one
/// strip marked ▶ "Video · 8 frames". A tap opens them full screen.
class MessageMedia extends StatelessWidget {
  const MessageMedia({super.key, required this.media});

  final List<MediaRef> media;

  @override
  Widget build(BuildContext context) {
    if (media.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: Tokens.space1),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final g in mediaGroups(media))
          g.video ? _VideoStrip(group: g, all: media) : _PhotoGrid(group: g, all: media),
      ]),
    );
  }
}

void _view(BuildContext context, List<MediaRef> all, MediaRef first) => Navigator.of(context).push(
      MaterialPageRoute<void>(
          fullscreenDialog: true, builder: (_) => MediaViewer(media: all, start: all.indexOf(first))),
    );

class _PhotoGrid extends StatelessWidget {
  const _PhotoGrid({required this.group, required this.all});
  final MediaGroup group;
  final List<MediaRef> all;

  @override
  Widget build(BuildContext context) => Wrap(spacing: Tokens.space1, runSpacing: Tokens.space1, children: [
        for (final m in group.items)
          GestureDetector(
            key: Key('media-${m.id}'),
            onTap: () => _view(context, all, m),
            child: MediaPicture(media: m, size: _thumb),
          ),
      ]);
}

class _VideoStrip extends StatelessWidget {
  const _VideoStrip({required this.group, required this.all});
  final MediaGroup group;
  final List<MediaRef> all;

  @override
  Widget build(BuildContext context) => GestureDetector(
        key: Key('media-${group.items.first.id}'),
        onTap: () => _view(context, all, group.items.first),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
            height: _frameThumb,
            child: ListView(scrollDirection: Axis.horizontal, shrinkWrap: true, children: [
              for (final m in group.items)
                Padding(
                    padding: const EdgeInsets.only(right: 2),
                    child: MediaPicture(media: m, size: _frameThumb)),
            ]),
          ),
          Row(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.play_arrow_rounded, size: 16, color: Tokens.textSecondary),
            Text(videoLabel(group.items.length),
                style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          ]),
        ]),
      );
}

/// One picture, square-cropped to [size]; a grey box while it loads or if it
/// can't be read.
class MediaPicture extends ConsumerWidget {
  const MediaPicture({super.key, required this.media, required this.size, this.fit = BoxFit.cover});

  final MediaRef media;
  final double? size;
  final BoxFit fit;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bytes = ref.watch(mediaBytesProvider(media.path)).valueOrNull;
    final box = Container(width: size, height: size, color: Tokens.raised);
    return ClipRRect(
      borderRadius: BorderRadius.circular(size == null ? 0 : Tokens.radiusSm),
      child: bytes == null
          ? box
          : Image.memory(bytes, width: size, height: size, fit: fit, errorBuilder: (_, _, _) => box),
    );
  }
}

/// Full screen: swipe between a message's pictures, pinch to zoom.
class MediaViewer extends StatelessWidget {
  const MediaViewer({super.key, required this.media, this.start = 0});

  final List<MediaRef> media;
  final int start;

  @override
  Widget build(BuildContext context) => Scaffold(
        key: const Key('media-viewer'),
        backgroundColor: Colors.black,
        appBar: AppBar(backgroundColor: Colors.black, foregroundColor: Tokens.text),
        body: PageView(
          controller: PageController(initialPage: start.clamp(0, media.length - 1)),
          children: [
            for (final m in media)
              InteractiveViewer(
                maxScale: 5,
                child: Center(child: MediaPicture(media: m, size: null, fit: BoxFit.contain)),
              ),
          ],
        ),
      );
}
