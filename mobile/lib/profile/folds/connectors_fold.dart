import 'package:flutter/material.dart';

import '../../connectors/connectors_list.dart';

/// Connectors (a service's web API with your key): list, add, edit, remove.
/// The key is write-only (see `ConnectorForm`).
class ConnectorsFold extends StatelessWidget {
  const ConnectorsFold({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context) => ConnectorsList(botId: botId);
}
