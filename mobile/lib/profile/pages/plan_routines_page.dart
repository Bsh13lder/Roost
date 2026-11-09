import 'package:flutter/material.dart';

import '../../plan/plan_tab.dart';
import '../../routines/bot_routines_list.dart';
import '../../theme/tokens.dart';

/// Plan & routines: the bot's Plan (Kanban · Calendar · Edit as text) with
/// its routines under it.
class PlanRoutinesPage extends StatelessWidget {
  const PlanRoutinesPage({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          backgroundColor: Tokens.bg, title: const Text('Plan & routines')),
      body: Column(children: [
        Expanded(flex: 7, child: PlanTab(botId: botId)),
        const Divider(height: 1, color: Tokens.border),
        Expanded(flex: 3, child: BotRoutinesList(botId: botId)),
      ]),
    );
  }
}
