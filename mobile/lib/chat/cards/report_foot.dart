import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import '../web_mark.dart';

const reminderFoot = '🔔 Reminder';
const footStyle = TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption);

/// The quiet grey line under a Report (owner, 2026-10-26: "like Grok"): where
/// it came from, small links, and the web mark.
class ReportFoot extends StatelessWidget {
  const ReportFoot(
      {super.key, required this.label, required this.tainted, this.links = const []});
  final String? label;
  final bool tainted;
  final List<Widget> links;

  @override
  Widget build(BuildContext context) {
    if (label == null && links.isEmpty && !tainted) return const SizedBox.shrink();
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: Tokens.space2,
      children: [
        if (label != null) Text(label!, style: footStyle),
        for (final link in links) ...[const Text('·', style: footStyle), link],
        if (tainted) const WebMark(),
      ],
    );
  }
}

/// A small quiet link in a Report's footer.
class FootLink extends StatelessWidget {
  const FootLink(this.label, {super.key, required this.semantics, required this.onTap});
  final String label;
  final String semantics;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
        label: semantics,
        button: true,
        excludeSemantics: true,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: Tokens.space1),
            child: Text(label, style: footStyle),
          ),
        ),
      );
}
