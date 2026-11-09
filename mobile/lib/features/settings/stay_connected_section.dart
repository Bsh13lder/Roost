import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../notify/notify_prefs.dart';
import '../../notify/notify_providers.dart';
import '../../util/app_time.dart';
import '../../widgets/grouped_card.dart';

const stayConnectedCaption =
    'Keeps a quiet link to your Mac over Tailscale, so alerts come at once. Nothing goes through Google. '
    'Android shows a small Roost icon while it is on.';
const batteryCaption = 'Some phones (Xiaomi too) stop apps in the background. Let Roost run so alerts keep coming.';

/// Whether Android may stop Roost to save battery (read when the screen opens).
final _batteryFreeProvider = FutureProvider.autoDispose<bool>(
    (ref) => ref.watch(stayConnectedProvider).batteryFree());

/// Stay connected, the kinds of alert, quiet hours and the battery setting.
class StayConnectedSection extends ConsumerStatefulWidget {
  const StayConnectedSection({super.key});

  @override
  ConsumerState<StayConnectedSection> createState() => _StayConnectedSectionState();
}

class _StayConnectedSectionState extends ConsumerState<StayConnectedSection> {
  String? _note;
  bool _busy = false;

  NotifyPrefsController get _prefs => ref.read(notifyPrefsProvider.notifier);

  Future<void> _stayConnected(bool on) async {
    setState(() {
      _busy = true;
      _note = null;
    });
    final note = await _prefs.setStayConnected(on);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _note = note;
    });
  }

  Future<void> _pickTime(NotifyPrefs p, {required bool from}) async {
    final minute = from ? p.quietFrom : p.quietTo;
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: minute ~/ 60, minute: minute % 60),
      helpText: from ? 'Quiet from (${zoneCity()})' : 'Quiet until (${zoneCity()})',
    );
    if (picked == null) return;
    final value = picked.hour * 60 + picked.minute;
    await _prefs.change(from ? p.copyWith(quietFrom: value) : p.copyWith(quietTo: value));
  }

  @override
  Widget build(BuildContext context) {
    final p = ref.watch(notifyPrefsProvider).valueOrNull ?? const NotifyPrefs();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      GroupedCard(caption: _note ?? stayConnectedCaption, children: [
        SwitchRow(
          switchKey: const Key('stay-connected'),
          label: 'Stay connected',
          value: p.stayConnected,
          onChanged: _busy ? null : _stayConnected,
        ),
      ]),
      if (p.stayConnected) ..._onParts(p),
    ]);
  }

  List<Widget> _onParts(NotifyPrefs p) {
    void set(NotifyPrefs next) => _prefs.change(next);
    return [
      GroupedCard(label: 'Tell me about', children: [
        SwitchRow(
            switchKey: const Key('alert-needs-ok'),
            label: 'Needs your OK',
            caption: 'Cards that wait for your answer or a sign-in',
            value: p.needsOk,
            onChanged: (v) => set(p.copyWith(needsOk: v))),
        SwitchRow(
            switchKey: const Key('alert-reminders'),
            label: 'Task reminders',
            value: p.reminders,
            onChanged: (v) => set(p.copyWith(reminders: v))),
        SwitchRow(
            switchKey: const Key('alert-reports'),
            label: 'Reports',
            caption: 'What a routine found',
            value: p.reports,
            onChanged: (v) => set(p.copyWith(reports: v))),
        SwitchRow(
            switchKey: const Key('alert-replies'),
            label: 'Replies',
            caption: "A bot's answer while Roost is closed",
            value: p.replies,
            onChanged: (v) => set(p.copyWith(replies: v))),
      ]),
      GroupedCard(
        label: 'Quiet hours',
        caption: '${zoneCity()} time. Your task reminders still come.',
        children: [
          SwitchRow(
              switchKey: const Key('quiet-on'),
              label: 'Quiet hours',
              value: p.quietOn,
              onChanged: (v) => set(p.copyWith(quietOn: v))),
          if (p.quietOn) ...[
            NavRow(label: 'From', value: clockText(p.quietFrom), onTap: () => _pickTime(p, from: true)),
            NavRow(label: 'Until', value: clockText(p.quietTo), onTap: () => _pickTime(p, from: false)),
          ],
        ],
      ),
      _battery(),
    ];
  }

  Widget _battery() {
    final free = ref.watch(_batteryFreeProvider).valueOrNull ?? true;
    if (free) return const SizedBox.shrink();
    return GroupedCard(caption: batteryCaption, children: [
      NavRow(
        key: const Key('battery-free'),
        label: 'Let Roost run in the background',
        icon: Icons.battery_alert_outlined,
        onTap: () async {
          await ref.read(stayConnectedProvider).openBatterySettings();
          ref.invalidate(_batteryFreeProvider);
        },
      ),
    ]);
  }
}
