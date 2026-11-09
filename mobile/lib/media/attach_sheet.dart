import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/tokens.dart';
import 'attachments.dart';
import 'media_source.dart';

enum AttachChoice { photo, camera, video, computer, password }

/// The composer's + menu: pictures and a video for the bot to look at, for a
/// bot on its Linux computer how it uses that computer, and Save a password
/// (to Vault: passwords, never to the chat).
Future<AttachChoice?> showAttachSheet(BuildContext context, {String? computerLabel}) =>
    showModalBottomSheet<AttachChoice>(
      context: context,
      // As tall as its rows, scrolling on a short screen.
      isScrollControlled: true,
      backgroundColor: Tokens.panel,
      builder: (sheet) => SafeArea(
        child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
          _row(sheet, AttachChoice.photo, Icons.photo_library_outlined, 'Photo', 'Up to $photosMax from your gallery'),
          _row(sheet, AttachChoice.camera, Icons.photo_camera_outlined, 'Camera', 'Take a picture now'),
          _row(sheet, AttachChoice.video, Icons.movie_outlined, 'Video',
              'Up to 2 minutes; the bot sees $videoFrames frames'),
          if (computerLabel != null)
            _row(sheet, AttachChoice.computer, Icons.computer_outlined, 'Computer', computerLabel),
          _row(sheet, AttachChoice.password, Icons.key_outlined, 'Save a password',
              'Kept sealed in Vault: passwords; the bot never sees it'),
        ])),
      ),
    );

Widget _row(BuildContext sheet, AttachChoice choice, IconData icon, String title, String subtitle) => ListTile(
      key: Key('attach-${choice.name}'),
      leading: Icon(icon),
      title: Text(title),
      subtitle: Text(subtitle),
      onTap: () => Navigator.pop(sheet, choice),
    );

/// Fetches what [choice] asks for into [botId]'s tray; a problem shows there.
Future<void> attach(WidgetRef ref, String botId, AttachChoice choice) async {
  final source = ref.read(mediaSourceProvider);
  final tray = ref.read(trayProvider(botId).notifier);
  try {
    switch (choice) {
      case AttachChoice.photo:
        final room = photosMax - ref.read(trayProvider(botId)).items.length;
        tray.addPhotos(await source.photos(room.clamp(0, photosMax)));
      case AttachChoice.camera:
        final shot = await source.camera();
        if (shot != null) tray.addPhotos([shot]);
      case AttachChoice.video:
        tray.addVideo(await source.videoFrames());
      case AttachChoice.computer:
      case AttachChoice.password:
        break;
    }
  } on MediaProblem catch (e) {
    tray.fail(e.message);
  } catch (_) {
    tray.fail("Couldn't open your pictures. Check Roost may use them in the phone's settings.");
  }
}
