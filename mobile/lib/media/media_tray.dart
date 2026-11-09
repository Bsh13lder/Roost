import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/tokens.dart';
import 'attachments.dart';
import 'media_ref.dart';

const _thumb = 64.0;

/// The pictures waiting above the composer, each with ×; a video is one tile.
/// While a Send uploads it shows how far it got; a failure shows why, and
/// Send again retries.
class MediaTray extends ConsumerWidget {
  const MediaTray({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tray = ref.watch(trayProvider(botId));
    if (tray.isEmpty && tray.error == null) return const SizedBox.shrink();
    final shown = tray.hasVideo ? [tray.items.first] : tray.items;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Tokens.space3, Tokens.space1, Tokens.space3, 0),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (shown.isNotEmpty)
          SizedBox(
            height: _thumb,
            child: ListView(scrollDirection: Axis.horizontal, children: [
              for (final a in shown) _Tile(attachment: a, frames: tray.hasVideo ? tray.items.length : 0,
                  busy: tray.busy, onRemove: () => ref.read(trayProvider(botId).notifier).remove(a.key)),
            ]),
          ),
        if (tray.busy)
          Padding(
            padding: const EdgeInsets.only(top: Tokens.space1),
            child: Text('Sending pictures… ${tray.done} of ${tray.items.length}',
                style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
          ),
        if (tray.error != null)
          Padding(
            padding: const EdgeInsets.only(top: Tokens.space1),
            child: Text(tray.error!, style: const TextStyle(color: Tokens.dangerText, fontSize: Tokens.fsLabel)),
          ),
      ]),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({required this.attachment, required this.frames, required this.busy, required this.onRemove});

  final Attachment attachment;
  final int frames;
  final bool busy;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) => Padding(
        key: const Key('tray-item'),
        padding: const EdgeInsets.only(right: Tokens.space2),
        child: Stack(children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(Tokens.radiusSm),
            child: Image.memory(attachment.bytes,
                width: frames > 0 ? _thumb * 2 : _thumb, height: _thumb, fit: BoxFit.cover,
                errorBuilder: (_, _, _) => Container(width: _thumb, height: _thumb, color: Tokens.raised)),
          ),
          if (frames > 0)
            Positioned(
              left: 4,
              bottom: 4,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                color: Tokens.bg.withValues(alpha: 0.7),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  const Icon(Icons.play_arrow_rounded, size: 14, color: Tokens.text),
                  Text(videoLabel(frames), style: const TextStyle(fontSize: Tokens.fsCaption)),
                ]),
              ),
            ),
          if (!busy)
            Positioned(
              right: 0,
              top: 0,
              child: GestureDetector(
                key: const Key('tray-remove'),
                onTap: onRemove,
                child: Container(
                  decoration: const BoxDecoration(color: Tokens.bg, shape: BoxShape.circle),
                  child: const Icon(Icons.close, size: 16, color: Tokens.text),
                ),
              ),
            ),
        ]),
      );
}
