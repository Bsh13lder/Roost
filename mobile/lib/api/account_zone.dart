import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../util/app_time.dart';
import 'providers.dart';

/// The signed-in account (`GET /api/auth/me`), read by screens shown only
/// while signed in, and asked again after a new sign-in.
final meProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  ref.listen(authProvider, (was, now) {
    // Not the start-up load of the kept session: only a new sign-in.
    if (was != null && was.ready && was.token != now.token) ref.invalidateSelf();
  });
  final data = await ref.watch(apiClientProvider).get('/api/auth/me');
  return data is Map ? data.cast<String, dynamic>() : const {};
});

/// The account's time zone (owner, 2026-11-09): the zone `/api/auth/me`
/// names becomes the app's zone and is kept for offline screens. A null or
/// unknown zone changes nothing (the web sets it), so the kept one, else
/// UTC, stays. Answers the zone's IANA name.
final accountZoneProvider = FutureProvider<String>((ref) async {
  final zone = (await ref.watch(meProvider.future))['timezone'];
  if (zone is String && setAppZone(zone)) {
    await ref.read(sessionStoreProvider).writeTimezone(zone);
  }
  return appZoneName();
});
