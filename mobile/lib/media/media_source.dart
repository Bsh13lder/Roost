
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

/// Frames taken from one video, and the longest clip the phone accepts.
const videoFrames = 8;
const videoMaxSeconds = 120;
const _pictureMaxSide = 2048.0;
const _pictureQuality = 85;
const framesChannelName = 'roost/frames';

/// Says why a video could not be read, in the owner's words.
class MediaProblem implements Exception {
  const MediaProblem(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Where the composer's pictures come from (fake in tests).
abstract class MediaSource {
  Future<List<Uint8List>> photos(int limit);
  Future<Uint8List?> camera();

  /// [videoFrames] evenly spaced JPEG frames of one clip the owner picks.
  Future<List<Uint8List>> videoFrames();
}

/// The phone's gallery and camera (image_picker), and the app's own Android
/// channel for a video's frames (MediaMetadataRetriever; no extra package).
class PhoneMediaSource implements MediaSource {
  PhoneMediaSource({ImagePicker? picker, MethodChannel? frames})
      : _picker = picker ?? ImagePicker(),
        _frames = frames ?? const MethodChannel(framesChannelName);

  final ImagePicker _picker;
  final MethodChannel _frames;

  @override
  Future<List<Uint8List>> photos(int limit) async {
    if (limit <= 0) return const [];
    final picked = limit == 1
        ? [?await _picker.pickImage(source: ImageSource.gallery, maxWidth: _pictureMaxSide,
              maxHeight: _pictureMaxSide, imageQuality: _pictureQuality)]
        : await _picker.pickMultiImage(
            limit: limit, maxWidth: _pictureMaxSide, maxHeight: _pictureMaxSide, imageQuality: _pictureQuality);
    return [for (final f in picked.take(limit)) await f.readAsBytes()];
  }

  @override
  Future<Uint8List?> camera() async {
    final shot = await _picker.pickImage(
        source: ImageSource.camera, maxWidth: _pictureMaxSide, maxHeight: _pictureMaxSide,
        imageQuality: _pictureQuality);
    return shot == null ? null : await shot.readAsBytes();
  }

  @override
  Future<List<Uint8List>> videoFrames() async {
    final clip = await _picker.pickVideo(
        source: ImageSource.gallery, maxDuration: const Duration(seconds: videoMaxSeconds));
    if (clip == null) return const [];
    try {
      final raw = await _frames.invokeListMethod<Uint8List>(
          'grab', {'path': clip.path, 'count': videoFrames, 'maxSeconds': videoMaxSeconds});
      return raw ?? const [];
    } on PlatformException catch (e) {
      throw MediaProblem(e.message ?? "Couldn't read that video.");
    }
  }
}

final mediaSourceProvider = Provider<MediaSource>((ref) => PhoneMediaSource());
