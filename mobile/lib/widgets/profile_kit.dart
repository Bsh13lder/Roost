import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../theme/tokens.dart';

/// A friendly sentence for any error.
String describe(Object error) =>
    error is ApiException ? error.message : 'Something went wrong. Try again.';

/// A grouped card of rows.
class InfoCard extends StatelessWidget {
  const InfoCard({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(
          horizontal: Tokens.space4, vertical: Tokens.space2),
      decoration: BoxDecoration(
        color: Tokens.panel,
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
        border: Border.all(color: Tokens.border),
      ),
      child: Column(children: children),
    );
  }
}

/// A label on the left, a value (or a trailing widget) on the right.
class InfoRow extends StatelessWidget {
  const InfoRow({
    super.key,
    required this.label,
    this.value,
    this.trailing,
    this.onTap,
  });

  final String label;
  final String? value;
  final Widget? trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: Tokens.space4, vertical: Tokens.space3),
        child: Row(children: [
          Text(label, style: const TextStyle(fontSize: Tokens.fsBody)),
          const SizedBox(width: Tokens.space3),
          Expanded(
            child: Align(
              alignment: Alignment.centerRight,
              child: trailing ??
                  Text(value ?? '',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: Tokens.fsBody,
                          color: Tokens.textSecondary)),
            ),
          ),
          if (onTap != null)
            const Icon(Icons.chevron_right, color: Tokens.textFaint, size: 20),
        ]),
      ),
    );
  }
}

/// A closed-until-opened section of the Info tab.
class Fold extends StatelessWidget {
  const Fold({super.key, required this.title, required this.child, this.summary});

  final String title;
  final String? summary;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(
          horizontal: Tokens.space4, vertical: Tokens.space2),
      decoration: BoxDecoration(
        color: Tokens.panel,
        borderRadius: BorderRadius.circular(Tokens.radiusLg),
        border: Border.all(color: Tokens.border),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          title: Text(title, style: const TextStyle(fontSize: Tokens.fsBody)),
          subtitle: summary == null
              ? null
              : Text(summary!,
                  style: const TextStyle(
                      fontSize: Tokens.fsCaption, color: Tokens.textSecondary)),
          childrenPadding: const EdgeInsets.fromLTRB(
              Tokens.space4, 0, Tokens.space4, Tokens.space3),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          maintainState: false,
          children: [child],
        ),
      ),
    );
  }
}

class Quiet extends StatelessWidget {
  const Quiet(this.text, {super.key, this.bad = false});

  final String text;
  final bool bad;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: Tokens.space2),
        child: Text(text,
            style: TextStyle(
                fontSize: Tokens.fsLabel,
                color: bad ? Tokens.dangerText : Tokens.textSecondary)),
      );
}

/// Loads once, shows the result, and hands the builder a reload.
class LoadView<T> extends StatefulWidget {
  const LoadView({super.key, required this.load, required this.builder});

  final Future<T> Function() load;
  final Widget Function(BuildContext, T data, Future<void> Function() reload)
      builder;

  @override
  State<LoadView<T>> createState() => _LoadViewState<T>();
}

class _LoadViewState<T> extends State<LoadView<T>> {
  late Future<T> _future = widget.load();

  Future<void> _reload() async {
    final next = widget.load();
    setState(() {
      _future = next;
    });
    await next.then((_) {}, onError: (_) {});
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: _future,
      builder: (context, snap) {
        if (snap.hasError) {
          return Row(children: [
            Expanded(child: Quiet(describe(snap.error!), bad: true)),
            TextButton(onPressed: _reload, child: const Text('Try again')),
          ]);
        }
        if (!snap.hasData) {
          return const Padding(
            padding: EdgeInsets.all(Tokens.space3),
            child: Center(
                child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))),
          );
        }
        return widget.builder(context, snap.data as T, _reload);
      },
    );
  }
}

/// Runs a save; on failure shows the friendly sentence in a snack bar.
Future<bool> attempt(BuildContext context, Future<void> Function() job) async {
  try {
    await job();
    return true;
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(describe(e))));
    }
    return false;
  }
}

Future<bool> confirm(BuildContext context, String title, String action,
    {String? body}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (c) => AlertDialog(
      title: Text(title),
      content: body == null ? null : Text(body),
      actions: [
        TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(c, true), child: Text(action)),
      ],
    ),
  );
  return ok == true;
}
