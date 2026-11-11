import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// The screens whose show / hide choices are kept apart (board toggles).
const screenTasks = 'tasks';
const screenKanban = 'kanban';
const screenCalendar = 'calendar';
const screenPlan = 'plan';

const _keyPrefix = 'roost_show_';

enum ShowToggle {
  routines('Routines'),
  done('Done'),
  botMade('Made by bots');

  const ShowToggle(this.label);
  final String label;
}

/// One screen's choices; everything shows until you hide it. Immutable.
@immutable
class ScreenToggles {
  const ScreenToggles({this.routines = true, this.done = true, this.botMade = true});

  /// Anything unreadable shows, so a bad value never hides things.
  factory ScreenToggles.fromJson(Object? raw) {
    if (raw is! Map) return const ScreenToggles();
    return ScreenToggles(
      routines: raw['routines'] != false,
      done: raw['done'] != false,
      botMade: raw['botMade'] != false,
    );
  }

  final bool routines;
  final bool done;
  final bool botMade;

  bool shows(ShowToggle t) => switch (t) {
        ShowToggle.routines => routines,
        ShowToggle.done => done,
        ShowToggle.botMade => botMade,
      };

  ScreenToggles flip(ShowToggle t) => ScreenToggles(
        routines: t == ShowToggle.routines ? !routines : routines,
        done: t == ShowToggle.done ? !done : done,
        botMade: t == ShowToggle.botMade ? !botMade : botMade,
      );

  Map<String, Object> toJson() => {'routines': routines, 'done': done, 'botMade': botMade};

  @override
  bool operator ==(Object other) =>
      other is ScreenToggles &&
      other.routines == routines &&
      other.done == done &&
      other.botMade == botMade;

  @override
  int get hashCode => Object.hash(routines, done, botMade);
}

/// Where the choices are kept between launches: on this phone only.
abstract interface class ScreenToggleStore {
  Future<ScreenToggles> load(String screen);
  Future<void> save(String screen, ScreenToggles toggles);
}

/// The phone's small key-value storage (the one the Tasks chips use). A
/// storage problem only means everything shows.
class DeviceScreenToggleStore implements ScreenToggleStore {
  const DeviceScreenToggleStore();

  @override
  Future<ScreenToggles> load(String screen) async {
    try {
      final raw = await FlutterForegroundTask.getData<String>(key: '$_keyPrefix$screen');
      return raw == null ? const ScreenToggles() : ScreenToggles.fromJson(jsonDecode(raw));
    } catch (e) {
      debugPrint('Show choices could not be read: $e');
      return const ScreenToggles();
    }
  }

  @override
  Future<void> save(String screen, ScreenToggles toggles) async {
    try {
      await FlutterForegroundTask.saveData(
          key: '$_keyPrefix$screen', value: jsonEncode(toggles.toJson()));
    } catch (e) {
      debugPrint('Show choices could not be kept: $e');
    }
  }
}

/// Tests: a store in memory.
class MemoryScreenToggleStore implements ScreenToggleStore {
  MemoryScreenToggleStore([Map<String, ScreenToggles>? saved]) : saved = {...?saved};

  final Map<String, ScreenToggles> saved;

  @override
  Future<ScreenToggles> load(String screen) async => saved[screen] ?? const ScreenToggles();

  @override
  Future<void> save(String screen, ScreenToggles toggles) async => saved[screen] = toggles;
}

final screenToggleStoreProvider =
    Provider<ScreenToggleStore>((_) => const DeviceScreenToggleStore());

/// A screen's choices: everything shown, then what this phone kept, unless
/// you flipped one first.
class ScreenTogglesController extends FamilyNotifier<ScreenToggles, String> {
  bool _touched = false;

  @override
  ScreenToggles build(String screen) {
    _touched = false;
    _load(screen);
    return const ScreenToggles();
  }

  Future<void> _load(String screen) async {
    final kept = await ref.read(screenToggleStoreProvider).load(screen);
    if (!_touched) state = kept;
  }

  void flip(ShowToggle t) {
    _touched = true;
    state = state.flip(t);
    ref.read(screenToggleStoreProvider).save(arg, state);
  }
}

final screenTogglesProvider =
    NotifierProvider.family<ScreenTogglesController, ScreenToggles, String>(
        ScreenTogglesController.new);

/// The Show button: a menu of ticked switches for one screen's [options].
class ShowMenuButton extends ConsumerWidget {
  const ShowMenuButton(
      {super.key, required this.screen, required this.options, this.done, this.onDone});

  final String screen;
  final List<ShowToggle> options;

  /// A screen whose Done lives elsewhere (the Tasks list's Done chip): its
  /// state and its flip, in place of this screen's kept choice.
  final bool? done;
  final VoidCallback? onDone;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final toggles = ref.watch(screenTogglesProvider(screen));
    return PopupMenuButton<ShowToggle>(
      key: Key('show-menu-$screen'),
      tooltip: 'Show',
      icon: const Icon(Icons.tune),
      onSelected: (t) => t == ShowToggle.done && onDone != null
          ? onDone!()
          : ref.read(screenTogglesProvider(screen).notifier).flip(t),
      itemBuilder: (_) => [
        for (final t in options)
          CheckedPopupMenuItem(
            key: Key('show-${t.name}'),
            value: t,
            checked: t == ShowToggle.done && done != null ? done! : toggles.shows(t),
            child: Text(t.label),
          ),
      ],
    );
  }
}
