import 'package:flutter/material.dart';

import '../../profile/folds/folders_fold.dart';
import '../../theme/tokens.dart';
import '../../widgets/grouped_card.dart';

/// Your Mac: folders, every bot's grant in one list. Revoke here; granting a
/// folder needs the Mac's folder window, so it stays on the web.
class MacFoldersScreen extends StatelessWidget {
  const MacFoldersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          backgroundColor: Tokens.bg, title: const Text('Your Mac: folders')),
      body: ListView(children: const [
        GroupedCard(
          caption: 'Share a new folder from a bot\'s Settings on the web.',
          children: [CardBody(child: FoldersFold(botId: null))],
        ),
      ]),
    );
  }
}
