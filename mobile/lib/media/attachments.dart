import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_error.dart';
import '../api/providers.dart';
import 'media_ref.dart';

/// The server's cap on pictures per message, and the phone's on photos.
const mediaMax = 8;
const photosMax = 4;
const videoTooBig = 'A video takes all 8 picture places. Remove the photos first.';
const tooManyPhotos = 'Up to 4 photos at a time.';

/// One picture waiting above the composer: a photo, or a frame of a video.
/// [uploaded] is set once the server took it, so a retry skips it.
class Attachment {
  const Attachment(this.key, this.bytes, {this.video = false, this.uploaded});

  final int key;
  final Uint8List bytes;
  final bool video;
  final MediaRef? uploaded;

  Attachment taken(MediaRef ref) => Attachment(key, bytes, video: video, uploaded: ref);
}

class TrayState {
  const TrayState(this.items, {this.busy = false, this.done = 0, this.error, this.nextKey = 0});

  factory TrayState.empty() => const TrayState([]);

  final List<Attachment> items;
  final bool busy;

  /// Pictures uploaded so far in this Send.
  final int done;
  final String? error;
  final int nextKey;

  bool get isEmpty => items.isEmpty;
  bool get hasVideo => items.any((a) => a.video);
  int get room => mediaMax - items.length;

  TrayState copy({List<Attachment>? items, bool? busy, int? done, String? Function()? error, int? nextKey}) =>
      TrayState(items ?? this.items,
          busy: busy ?? this.busy,
          done: done ?? this.done,
          error: error != null ? error() : this.error,
          nextKey: nextKey ?? this.nextKey);

  TrayState _added(List<Uint8List> pictures, {required bool video}) => copy(
        items: [
          ...items,
          for (var i = 0; i < pictures.length; i++) Attachment(nextKey + i, pictures[i], video: video),
        ],
        nextKey: nextKey + pictures.length,
        error: () => null,
      );

  TrayState withPhotos(List<Uint8List> photos) {
    final photoCount = items.where((a) => !a.video).length;
    if (hasVideo || photoCount + photos.length > photosMax) return copy(error: () => hasVideo ? videoTooBig : tooManyPhotos);
    return _added(photos, video: false);
  }

  TrayState withVideo(List<Uint8List> frames) {
    if (items.isNotEmpty || frames.length > mediaMax) return copy(error: () => videoTooBig);
    return _added(frames, video: true);
  }

  /// A photo goes alone; a video's frames all go together.
  TrayState without(int key) {
    final gone = items.firstWhere((a) => a.key == key, orElse: () => items.first);
    return copy(items: [for (final a in items) if (a.key != key && !(gone.video && a.video)) a], error: () => null);
  }
}

/// The pictures waiting in one bot's composer.
class TrayController extends FamilyNotifier<TrayState, String> {
  @override
  TrayState build(String arg) => TrayState.empty();

  void addPhotos(List<Uint8List> photos) {
    if (photos.isNotEmpty) state = state.withPhotos(photos);
  }

  void addVideo(List<Uint8List> frames) {
    if (frames.isNotEmpty) state = state.withVideo(frames);
  }

  void remove(int key) => state = state.without(key);

  void clear() => state = TrayState.empty();

  void fail(String message) => state = state.copy(error: () => message);

  /// Uploads every picture not yet taken, in order, and returns them all;
  /// null (with the reason in [TrayState.error]) when one fails.
  Future<List<MediaRef>?> upload(String threadId) async {
    final api = ref.read(apiClientProvider);
    state = state.copy(busy: true, done: 0, error: () => null);
    final taken = <MediaRef>[];
    for (final a in state.items) {
      final media = a.uploaded ?? await _one(api, threadId, a);
      if (media == null) return null;
      taken.add(media);
      state = state.copy(
          items: [for (final b in state.items) b.key == a.key ? b.taken(media) : b], done: taken.length);
    }
    state = state.copy(busy: false);
    return taken;
  }

  Future<MediaRef?> _one(ApiClient api, String threadId, Attachment a) async {
    final form = FormData.fromMap({
      'file': MultipartFile.fromBytes(a.bytes, filename: 'picture.${_extension(a.bytes)}',
          contentType: DioMediaType('image', _extension(a.bytes) == 'jpg' ? 'jpeg' : _extension(a.bytes))),
      if (a.video) 'video': '1',
    });
    try {
      final r = await api.post('/api/threads/${Uri.encodeComponent(threadId)}/media', form,
          const Duration(seconds: 60));
      final j = (r as Map).cast<String, dynamic>();
      return MediaRef(
          id: j['id'] as String,
          width: (j['width'] as num?)?.toInt() ?? 0,
          height: (j['height'] as num?)?.toInt() ?? 0,
          fromBot: false,
          video: a.video);
    } on ApiException catch (e) {
      state = state.copy(busy: false, error: () => e.message);
      return null;
    }
  }
}

String _extension(Uint8List b) {
  if (b.length > 3 && b[0] == 0x89 && b[1] == 0x50) return 'png';
  if (b.length > 11 && b[8] == 0x57 && b[9] == 0x45 && b[10] == 0x42 && b[11] == 0x50) return 'webp';
  return 'jpg';
}

final trayProvider = NotifierProvider.family<TrayController, TrayState, String>(TrayController.new);
