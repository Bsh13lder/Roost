import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../api/providers.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'bot_detail.dart';

const pictureMaxSide = 256.0; // the web shrinks to 256 px too
const pictureMaxBytes = 512 * 1024; // AVATAR_PICTURE_MAX_BYTES

/// The picture's type from its first bytes (the gateway checks them too), or
/// null when it is not a PNG, JPEG or WebP.
String? pictureMime(Uint8List b) {
  bool starts(List<int> m, [int at = 0]) =>
      b.length >= at + m.length &&
      [for (var i = 0; i < m.length; i++) b[at + i] == m[i]].every((x) => x);
  if (starts([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])) {
    return 'image/png';
  }
  if (starts([0xFF, 0xD8, 0xFF])) return 'image/jpeg';
  if (starts([0x52, 0x49, 0x46, 0x46]) && starts([0x57, 0x45, 0x42, 0x50], 8)) {
    return 'image/webp';
  }
  return null;
}

/// Upload or remove the bot's own picture; its Lensbot shows it on the web.
class PictureRow extends ConsumerStatefulWidget {
  const PictureRow({super.key, required this.botId, required this.hasPicture});

  final String botId;
  final bool hasPicture;

  @override
  ConsumerState<PictureRow> createState() => _PictureRowState();
}

class _PictureRowState extends ConsumerState<PictureRow> {
  late bool _has = widget.hasPicture;
  bool _busy = false;

  Future<void> _upload() async {
    final file = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      maxWidth: pictureMaxSide,
      maxHeight: pictureMaxSide,
      imageQuality: 85,
    );
    if (file == null || !mounted) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    final mime = pictureMime(bytes);
    if (mime == null) {
      return _say('Upload a PNG, JPEG or WebP picture.');
    }
    if (bytes.length > pictureMaxBytes) {
      return _say('That picture is too big (512 KB at most). Try a smaller one.');
    }
    await _run(() => ref
        .read(apiClientProvider)
        .postBytes('/api/bots/${widget.botId}/picture', bytes, mime), true);
  }

  Future<void> _remove() => _run(
      () => ref.read(apiClientProvider).delete('/api/bots/${widget.botId}/picture'),
      false);

  Future<void> _run(Future<dynamic> Function() call, bool now) async {
    setState(() => _busy = true);
    final id = widget.botId;
    final ok = await attempt(context, () async {
      final saved = await call();
      ref.read(botDetailProvider(id).notifier).replace(saved);
    });
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (ok) _has = now;
    });
    if (ok) _say(now ? 'Picture saved.' : 'Picture removed.');
  }

  void _say(String text) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(text)));

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      OutlinedButton.icon(
        key: const Key('upload-picture'),
        icon: const Icon(Icons.image_outlined),
        label: Text(_has ? 'Change picture' : 'Upload a picture'),
        onPressed: _busy ? null : _upload,
      ),
      if (_has) ...[
        const SizedBox(width: Tokens.space2),
        TextButton(
            key: const Key('remove-picture'),
            onPressed: _busy ? null : _remove,
            child: const Text('Remove')),
      ],
    ]);
  }
}
