import 'package:flutter/material.dart';

import '../../board/tasks/quick_add.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import 'paste_catch.dart';
import 'section_switch.dart';

/// The round "Add or find anything…" field with its + button.
class BarPill extends StatelessWidget {
  const BarPill({
    super.key,
    required this.controller,
    required this.focusNode,
    required this.busy,
    required this.onChanged,
    required this.onAdd,
    required this.onPaste,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool busy;
  final ValueChanged<String> onChanged;
  final VoidCallback onAdd;

  /// Paste (the field's menu, Ctrl+V or Cmd+V): the bar reads the clipboard
  /// itself, so a pasted list keeps its lines.
  final VoidCallback onPaste;

  @override
  Widget build(BuildContext context) {
    final typed = controller.text.trim().isNotEmpty;
    return Container(
      height: workBarHeight,
      decoration: BoxDecoration(
        color: Tokens.panel,
        borderRadius: BorderRadius.circular(workBarHeight / 2),
        border: Border.all(
          color: focusNode.hasFocus
              ? AccentColors.of(context).tint
              : Tokens.border,
        ),
      ),
      padding: const EdgeInsets.only(left: Tokens.space3),
      child: Row(
        children: [
          Icon(
            typed ? Icons.add : Icons.search,
            color: Tokens.textSecondary,
            size: 20,
          ),
          const SizedBox(width: Tokens.space2),
          Expanded(
            child: PasteCatcher(
              onPaste: onPaste,
              child: TextField(
                key: const Key('work-bar'),
                controller: controller,
                focusNode: focusNode,
                contextMenuBuilder: pasteMenu(onPaste),
                onChanged: onChanged,
                onSubmitted: (_) => onAdd(),
                maxLength: maxQuickLine,
                textInputAction: TextInputAction.done,
                decoration: const InputDecoration(
                  hintText: 'Add or find anything…',
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  filled: false,
                  isDense: true,
                  counterText: '',
                ),
              ),
            ),
          ),
          if (typed)
            IconButton(
              key: const Key('work-bar-add'),
              tooltip: 'Add as a task',
              onPressed: busy ? null : onAdd,
              icon: Icon(
                Icons.add_circle,
                color: AccentColors.of(context).strong,
              ),
            ),
        ],
      ),
    );
  }
}
