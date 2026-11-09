import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../api/models.dart';
import '../../live/live_connection.dart';
import '../../theme/tokens.dart';
import '../../util/app_time.dart';
import '../../widgets/lensbot.dart';
import '../../home/my_turn.dart';
import '../../update/update_banner.dart';
import '../../update/update_controller.dart';
import 'chat_search.dart';
import 'home_data.dart';
import 'sections.dart';

/// The bottom bar's height: the grid button and the search pill.
const _barHeight = 52.0;

const _pill = OutlineInputBorder(
  borderRadius: BorderRadius.all(Radius.circular(_barHeight / 2)),
  borderSide: BorderSide(color: Tokens.border),
);

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  final _search = TextEditingController();
  bool _searching = false;
  Timer? _debounce;
  String _hitQuery = '';

  @override
  void initState() {
    super.initState();
    // The update check on start: quiet, so a Mac that is away says nothing.
    Future.microtask(() => ref.read(updateProvider.notifier).check(quiet: true));
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onSearchChanged() {
    setState(() => _searching = _search.text.isNotEmpty);
    _debounce?.cancel();
    final text = _search.text.trim();
    _debounce = Timer(chatSearchDebounce, () {
      if (!mounted) return;
      setState(() => _hitQuery = text.length < chatSearchMinChars
          ? ''
          : text.substring(0, text.length > 100 ? 100 : text.length));
    });
  }

  List<Widget> _hits() {
    if (_hitQuery.isEmpty) return const [];
    final hits = ref.watch(chatSearchProvider(_hitQuery));
    return hits.when(
      loading: () => const [],
      error: (e, _) => const [],
      data: (list) => [
        if (list.isNotEmpty) const _Heading('Messages'),
        for (final h in list)
          ListTile(
            key: Key('hit-${h.messageId}'),
            title: Text(h.name, maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text(h.snippet,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Tokens.textSecondary)),
            trailing: h.createdAt.isEmpty
                ? null
                : Text(appClock(h.createdAt),
                    style: const TextStyle(
                        color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
            onTap: () => h.isBot ? context.push('/chat/${h.chatId}') : _soon('Rooms'),
          ),
      ],
    );
  }

  void _soon(String what) {
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text('$what is coming soon.')));
  }

  @override
  Widget build(BuildContext context) {
    final load = ref.watch(botsLoadProvider);
    final bots = ref.watch(liveProvider).bots;
    final chats = ref.watch(chatsProvider);
    return Scaffold(
      appBar: _topBar(),
      body: load.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _Problem('$e', () => ref.invalidate(botsLoadProvider)),
        data: (_) => ListView(
          children: [
            const UpdateBanner(),
            _AvatarRow(bots: avatarRow(bots.values), onOpen: _openBot),
            const MyTurn(),
            ..._chatList(chats, bots),
            ..._hits(),
          ],
        ),
      ),
      bottomNavigationBar: _bottomBar(),
    );
  }

  PreferredSizeWidget _topBar() {
    final name = ref.watch(usernameProvider).valueOrNull ?? '';
    return AppBar(
      backgroundColor: Tokens.bg,
      automaticallyImplyLeading: false,
      leading: Padding(
        padding: const EdgeInsets.all(Tokens.space2),
        child: InkWell(
          key: const Key('initials'),
          customBorder: const CircleBorder(),
          onTap: () => context.push('/settings'),
          child: CircleAvatar(
            backgroundColor: Tokens.raised,
            child: Text(initialsOf(name),
                style: const TextStyle(color: Tokens.text, fontSize: Tokens.fsLabel)),
          ),
        ),
      ),
      actions: [
        Padding(
          padding: const EdgeInsets.only(right: Tokens.space2),
          child: IconButton.filledTonal(
            key: const Key('new-bot'),
            tooltip: 'New bot',
            style: IconButton.styleFrom(backgroundColor: Tokens.raised),
            icon: const Icon(Icons.add),
            onPressed: () => context.push('/new-bot'),
          ),
        ),
      ],
    );
  }

  void _openBot(Bot bot) => context.push('/chat/${bot.id}');

  List<Widget> _chatList(AsyncValue<List<ChatRow>> chats, Map<String, Bot> bots) {
    return chats.when(
      loading: () => const [Padding(
        padding: EdgeInsets.all(Tokens.space6),
        child: Center(child: CircularProgressIndicator()),
      )],
      error: (e, _) => [_Problem('$e', () => ref.invalidate(chatsProvider))],
      data: (rows) {
        final sections = chatSections(rows, bots, _search.text);
        if (sections.isEmpty) {
          return const [Padding(
            padding: EdgeInsets.all(Tokens.space6),
            child: Center(
              child: Text('No chats found.',
                  style: TextStyle(color: Tokens.textSecondary)),
            ),
          )];
        }
        return [
          for (final s in sections) ...[
            if (s.label != null) _Heading(s.label!),
            for (final r in s.rows)
              _ChatTile(row: r, bot: bots[r.id], onTap: () => _tap(r, bots)),
          ],
        ];
      },
    );
  }

  void _tap(ChatRow row, Map<String, Bot> bots) {
    if (row.isBot) {
      context.push('/chat/${row.id}');
    } else {
      _soon('Rooms');
    }
  }

  Widget _bottomBar() {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(Tokens.space3),
        child: Row(
          children: [
            IconButton.filledTonal(
              key: const Key('board'),
              tooltip: 'Workspace',
              style: IconButton.styleFrom(
                  backgroundColor: Tokens.raised,
                  minimumSize: const Size.square(_barHeight)),
              icon: const Icon(Icons.grid_view_rounded),
              onPressed: () => context.push('/board'),
            ),
            const SizedBox(width: Tokens.space3),
            Expanded(child: _searchField()),
          ],
        ),
      ),
    );
  }

  Widget _searchField() {
    return TextField(
      key: const Key('search'),
      controller: _search,
      onChanged: (_) => _onSearchChanged(),
      decoration: InputDecoration(
        hintText: 'Search',
        isDense: true,
        border: _pill,
        enabledBorder: _pill,
        focusedBorder: _pill,
        constraints: const BoxConstraints(minHeight: _barHeight),
        prefixIcon: const Icon(Icons.search, size: 20),
        suffixIcon: _searching
            ? IconButton(
                icon: const Icon(Icons.close, size: 18),
                onPressed: () => setState(() {
                  _search.clear();
                  _searching = false;
                  _hitQuery = '';
                }),
              )
            : null,
      ),
    );
  }
}

class _AvatarRow extends StatelessWidget {
  const _AvatarRow({required this.bots, required this.onOpen});

  final List<Bot> bots;
  final void Function(Bot) onOpen;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 112,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
        children: [
          for (final bot in bots)
            InkWell(
              key: Key('avatar-${bot.id}'),
              onTap: () => onOpen(bot),
              child: Padding(
                padding: const EdgeInsets.all(Tokens.space2),
                child: Column(
                  children: [
                    LensbotAvatar(
                      avatar: bot.avatar,
                      size: 68,
                      star: bot.isPrimary,
                      status: bot.status,
                    ),
                    const SizedBox(height: Tokens.space1),
                    SizedBox(
                      width: 72,
                      child: Text(bot.name,
                          maxLines: 1,
                          textAlign: TextAlign.center,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: Tokens.fsLabel)),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(
            Tokens.space4, Tokens.space4, Tokens.space4, Tokens.space1),
        child: Text(text.toUpperCase(),
            style: const TextStyle(
              color: Tokens.textFaint,
              fontSize: Tokens.fsCaption,
              letterSpacing: 0.8,
            )),
      );
}

class _ChatTile extends StatelessWidget {
  const _ChatTile({required this.row, required this.bot, required this.onTap});

  final ChatRow row;
  final Bot? bot;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final preview = previewLine(row);
    return ListTile(
      key: Key('chat-${row.id}'),
      onTap: onTap,
      leading: bot == null
          ? const CircleAvatar(
              backgroundColor: Tokens.raised, child: Icon(Icons.groups, size: 20))
          : LensbotAvatar(avatar: bot!.avatar, size: 44, star: bot!.isPrimary),
      title: Text(row.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: preview.isEmpty
          ? null
          : Text(preview,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Tokens.textSecondary)),
      trailing: row.lastAt.isEmpty
          ? null
          : Text(appClock(row.lastAt),
              style: const TextStyle(
                  color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
    );
  }
}

class _Problem extends StatelessWidget {
  const _Problem(this.message, this.retry);

  final String message;
  final VoidCallback retry;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(Tokens.space6),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Tokens.dangerText)),
            const SizedBox(height: Tokens.space3),
            TextButton(onPressed: retry, child: const Text('Try again')),
          ],
        ),
      );
}
