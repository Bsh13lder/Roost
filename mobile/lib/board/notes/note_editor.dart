import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/raw_request.dart';
import '../common/widgets.dart';
import 'notes_api.dart';

const _changedElsewhere = 'Changed elsewhere';

/// Opens a note (or a new one when [noteId] is null) as markdown source with a
/// preview. Every save carries the revision it was opened at; a stale one
/// answers 409 and the screen shows "Changed elsewhere" with the current copy.
class NoteEditorScreen extends ConsumerStatefulWidget {
  const NoteEditorScreen({super.key, this.noteId, this.projectId});

  final String? noteId;
  final String? projectId;

  @override
  ConsumerState<NoteEditorScreen> createState() => _NoteEditorState();
}

class _NoteEditorState extends ConsumerState<NoteEditorScreen> {
  final _title = TextEditingController();
  final _content = TextEditingController();
  String? _id;
  int _revision = 0;
  bool _loading = true;
  bool _busy = false;
  bool _preview = false;
  String? _problem;
  Json? _conflict; // the stored copy after a 409

  @override
  void initState() {
    super.initState();
    _id = widget.noteId;
    _id == null ? _loading = false : _load();
  }

  @override
  void dispose() {
    _title.dispose();
    _content.dispose();
    super.dispose();
  }

  void _apply(Json note) {
    _title.text = note['title'] as String? ?? '';
    _content.text = note['content'] as String? ?? '';
    _revision = note['revision'] as int;
  }

  Future<void> _load() async {
    try {
      final note = await ref.read(notesApiProvider).get(_id!);
      if (mounted) setState(() { _apply(note); _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _problem = errorText(e); _loading = false; });
    }
  }

  Future<void> _save() async {
    if (_busy) return;
    setState(() { _busy = true; _problem = null; });
    final api = ref.read(notesApiProvider);
    try {
      final saved = _id == null
          ? await api.create(
              title: _title.text.trim(),
              content: _content.text,
              projectId: widget.projectId)
          : await api.save(_id!,
              baseRevision: _revision,
              title: _title.text.trim(),
              content: _content.text);
      if (!mounted) return;
      setState(() { _id = saved['id'] as String; _revision = saved['revision'] as int; _conflict = null; });
      snack(context, 'Saved');
    } on RevisionConflict catch (c) {
      if (mounted) setState(() => _conflict = c.current);
    } catch (e) {
      if (mounted) setState(() => _problem = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Keep mine: the stored copy's revision becomes the base, so the next Save wins.
  void _keepMine() => setState(() { _revision = _conflict!['revision'] as int; _conflict = null; });

  void _loadLatest() => setState(() { _apply(_conflict!); _conflict = null; });

  Future<void> _delete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Delete this note?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await ref.read(notesApiProvider).delete(_id!);
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) setState(() => _problem = errorText(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Tokens.bg,
      appBar: AppBar(
        title: Text(_id == null ? 'New note' : 'Note'),
        actions: [
          IconButton(
            tooltip: _preview ? 'Edit' : 'Preview',
            onPressed: () => setState(() => _preview = !_preview),
            icon: Icon(_preview ? Icons.edit_outlined : Icons.visibility_outlined),
          ),
          if (_id != null)
            IconButton(
                tooltip: 'Delete', onPressed: _delete, icon: const Icon(Icons.delete_outline)),
          TextButton(onPressed: _busy ? null : _save, child: const Text('Save')),
        ],
      ),
      body: _loading ? const BoardNote('Loading…') : _body(),
    );
  }

  Widget _body() => Column(children: [
        if (_conflict != null) _conflictBanner(),
        if (_problem != null) BoardNote(_problem!, error: true),
        Padding(
          padding: const EdgeInsets.all(Tokens.space4),
          child: TextField(
            controller: _title,
            decoration: const InputDecoration(hintText: 'Title'),
          ),
        ),
        Expanded(
          child: _preview
              ? Markdown(data: _content.text)
              : Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
                  child: TextField(
                    controller: _content,
                    maxLines: null,
                    expands: true,
                    textAlignVertical: TextAlignVertical.top,
                    decoration: const InputDecoration(hintText: 'Write in Markdown'),
                  ),
                ),
        ),
      ]);

  Widget _conflictBanner() => Container(
        key: const ValueKey('conflict'),
        width: double.infinity,
        color: Tokens.raised,
        padding: const EdgeInsets.all(Tokens.space4),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text(_changedElsewhere,
              style: TextStyle(color: Tokens.warn, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(
            'Someone saved a newer copy. Latest: “${_conflict!['title']}”. '
            '${(_conflict!['snippet'] as String?) ?? ''}',
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Tokens.textSecondary),
          ),
          Row(children: [
            TextButton(onPressed: _loadLatest, child: const Text('Load the latest')),
            TextButton(onPressed: _keepMine, child: const Text('Keep mine')),
          ]),
        ]),
      );
}
