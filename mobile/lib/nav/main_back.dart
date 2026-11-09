import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

/// Home, the main menu: every screen's Back ends here.
const homeRoute = '/';

/// The Board, where a project's page goes back to.
const _boardRoute = '/board';

/// A bot's own pages, whose Back opens that bot's chat.
final _botPage = RegExp(r'^/(?:profile|computer|bots)/([^/]+)(?:/.*)?$');

/// Where Back goes from [location] (owner, 2026-11-04: "from a bot, Back goes
/// to the main menu"): a bot's Profile, Computer or run log opens its chat,
/// a project's page the Board, everything else Home; null on Home means Back
/// leaves the app. It never walks back through the pages you came by.
String? backTarget(String location) {
  if (location == homeRoute) return null;
  final bot = _botPage.firstMatch(location);
  if (bot != null) return '/chat/${bot.group(1)}';
  if (location.startsWith('$_boardRoute/')) return _boardRoute;
  return homeRoute;
}

/// Back from the page holding [context]: a fresh stack with only the page
/// [backTarget] names, or out of the app from Home.
void goBack(BuildContext context) {
  // A page opened outside the router just closes, as before.
  if (GoRouter.maybeOf(context) == null) {
    Navigator.of(context).pop();
    return;
  }
  final target = backTarget(GoRouterState.of(context).uri.path);
  if (target == null) {
    SystemNavigator.pop();
  } else {
    context.go(target);
  }
}

/// Wraps one of the app's screens so that Back (the phone's or the app
/// bar's arrow) goes up to its parent page, and from a chat to Home, instead
/// of back through the pages you came by. Sheets, dialogs and pickers are
/// routes above the screen, so Back still closes them first.
class MainBackScope extends StatelessWidget {
  const MainBackScope({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return PopScope<Object?>(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        // Something drawn inside this page (a drawer) closes first.
        final route = ModalRoute.of(context);
        if (route != null && route.willHandlePopInternally) {
          Navigator.of(context).pop();
          return;
        }
        goBack(context);
      },
      child: child,
    );
  }
}
