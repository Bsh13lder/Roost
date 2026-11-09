import 'dart:async';

import 'package:roost_mobile/util/app_time.dart';

/// Every test starts on Madrid's clock, the zone the expectations were
/// written for; a test that changes it sets it back.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  setAppZone('Europe/Madrid');
  await testMain();
}
