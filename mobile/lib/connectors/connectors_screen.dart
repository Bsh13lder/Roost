import 'package:flutter/material.dart';

import '../theme/tokens.dart';
import 'connectors_list.dart';

/// All connectors, from the settings sheet.
class ConnectorsScreen extends StatelessWidget {
  const ConnectorsScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Connectors')),
        body: const SingleChildScrollView(
          padding: EdgeInsets.all(Tokens.space4),
          child: ConnectorsList(),
        ),
      );
}
