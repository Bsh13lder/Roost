import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'api/account_zone.dart';
import 'api/providers.dart';
import 'api/reachability.dart';
import 'workspace/workspace_screen.dart';
import 'board/projects/project_routes.dart';
import 'board/tasks/offline/offline_sync.dart';
import 'board/tasks/offline/offline_tasks_screen.dart';
import 'features/auth/sign_in_screen.dart';
import 'computer/computer_screen.dart';
import 'features/chat/computer_steps.dart';
import 'features/chat/run_steps.dart';
import 'features/chat/chat_screen.dart';
import 'features/home/home_screen.dart';
import 'features/offline/offline_screen.dart';
import 'features/settings/mac_folders_screen.dart';
import 'features/settings/notifications_screen.dart';
import 'features/settings/settings_screen.dart';
import 'connectors/connectors_screen.dart';
import 'payments/payment_cards_screen.dart';
import 'vault/vault_passwords_screen.dart';
import 'home/new_bot_screen.dart';
import 'nav/main_back.dart';
import 'notify/alert_taps.dart';
import 'notify/notify_providers.dart';
import 'profile/profile_screen.dart';
import 'routines/routines_screen.dart';
import 'routines/run_log_screen.dart';
import 'skills/skills_screen.dart';
import 'theme/accent.dart';
import 'theme/app_theme.dart';
import 'theme/tokens.dart';

/// A screen whose Back goes up to its parent page (a chat's to Home).
GoRoute _main(String path, Widget Function(GoRouterState state) build) =>
    GoRoute(
      path: path,
      builder: (_, state) => MainBackScope(child: build(state)),
    );

/// Rebuilds the router's redirect when the sign-in changes.
class _AuthListenable extends ChangeNotifier {
  void poke() => notifyListeners();
}

final routerProvider = Provider<GoRouter>((ref) {
  final listenable = _AuthListenable();
  ref.listen(authProvider, (a, b) => listenable.poke());
  ref.onDispose(listenable.dispose);
  final router = GoRouter(
    refreshListenable: listenable,
    redirect: (context, state) {
      final auth = ref.read(authProvider);
      if (!auth.ready) return state.matchedLocation == '/splash' ? null : '/splash';
      final onSignIn = state.matchedLocation == '/sign-in';
      if (!auth.signedIn) return onSignIn ? null : '/sign-in';
      if (onSignIn || state.matchedLocation == '/splash') return '/';
      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (a, b) => const _Splash()),
      GoRoute(path: '/sign-in', builder: (a, b) => const SignInScreen()),
      _main('/', (_) => const HomeScreen()),
      _main('/board', (_) => const WorkspaceScreen()),
      _main(projectPagePath, projectPageFor),
      _main('/new-bot', (_) => const NewBotScreen()),
      _main('/routines', (_) => const RoutinesScreen()),
      _main('/skills', (_) => const SkillsScreen()),
      _main('/connectors', (_) => const ConnectorsScreen()),
      _main('/payment-cards', (_) => const PaymentCardsScreen()),
      _main('/vault-passwords', (_) => const VaultPasswordsScreen()),
      _main('/settings', (_) => const SettingsScreen()),
      _main('/mac-folders', (_) => const MacFoldersScreen()),
      _main('/notifications', (_) => const NotificationsScreen()),
      // Leaving the offline screen brings you back where you were.
      GoRoute(path: '/offline', builder: (a, b) => const OfflineScreen()),
      // Your tasks with no connection, opened from the offline screen.
      GoRoute(
          path: offlineTasksPath,
          builder: (a, b) => const OfflineTasksScreen()),
      _main(
        '/bots/:botId/routines/:routineId/log',
        (state) => RunLogScreen(
          botId: state.pathParameters['botId']!,
          routineId: state.pathParameters['routineId']!,
        ),
      ),
      // The computer handles Back itself: while you hold control it asks
      // first, otherwise it goes to its bot's chat.
      GoRoute(
        path: '/computer/:botId',
        builder: (_, state) => ComputerScreen(
            botId: state.pathParameters['botId']!,
            go: state.uri.queryParameters['go']),
      ),
      _main('/profile/:botId',
          (state) => ProfileScreen(botId: state.pathParameters['botId']!)),
      _main('/chat/:botId',
          (state) => ChatScreen(botId: state.pathParameters['botId']!)),
    ],
  );
  // A tapped alert opens its bot's chat.
  openTappedAlerts(router.push).ignore();
  // The offline screen goes on top of wherever you were, so leaving it
  // brings you back there.
  ref.listen<bool>(offlineProvider, (was, now) {
    final fresh = now && was != true;
    if (fresh && ref.read(authProvider).signedIn) router.push('/offline');
  });
  return router;
});

class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) => const Scaffold(
        backgroundColor: Tokens.bg,
        body: Center(child: CircularProgressIndicator()),
      );
}

class RoostApp extends ConsumerWidget {
  const RoostApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = buildTheme(ref.watch(accentProvider));
    // Follow computer steps from the first frame, so a chat opened later
    // still shows the run already going.
    ref.listen(computerRunsProvider, (_, _) {});
    ref.listen(activityRunsProvider, (_, _) {});
    // The account's time zone, from /api/auth/me once signed in (before
    // that the kept one shows).
    if (ref.watch(authProvider.select((a) => a.signedIn))) {
      ref.listen(accountZoneProvider, (_, _) {});
    }
    // Sends what was done offline once Roost answers again.
    ref.listen(offlineSyncProvider, (_, _) {});
    // Keeps Stay connected told what you are looking at.
    ref.watch(stayConnectedSyncProvider);
    return MaterialApp.router(
      title: 'Roost',
      theme: theme,
      themeMode: ThemeMode.dark,
      darkTheme: theme,
      routerConfig: ref.watch(routerProvider),
      builder: (context, child) => _FocusReporter(child: child ?? const SizedBox()),
    );
  }
}


/// Tells the app's focus whether Roost is in front of you.
class _FocusReporter extends ConsumerStatefulWidget {
  const _FocusReporter({required this.child});

  final Widget child;

  @override
  ConsumerState<_FocusReporter> createState() => _FocusReporterState();
}

class _FocusReporterState extends ConsumerState<_FocusReporter> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    ref.read(appVisibleProvider.notifier).state = state == AppLifecycleState.resumed;
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
