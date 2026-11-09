import 'mentions.dart';

/// One run of your message: plain text, or a "#Name" token of a known project.
class ProjectSegment {
  const ProjectSegment(this.text, [this.project]);
  final String text;
  final MentionOption? project;
}

String _escape(String s) => s.replaceAllMapped(
    RegExp(r'[.*+?^${}()|[\]\\]'), (m) => '\\${m[0]}');

/// "#Project Name" in your own chat messages, read like the server's
/// roost/projects/chat_refs.py: exact names, any case, longest first, never
/// inside a word, so a chip is exactly the project the bot was told about.
List<ProjectSegment> splitProjectTokens(
    String text, List<MentionOption> projects) {
  if (projects.isEmpty || !text.contains('#')) return [ProjectSegment(text)];
  final names = [for (final p in projects) p.name]
    ..sort((a, b) => b.length.compareTo(a.length));
  final byName = {for (final p in projects) p.name.toLowerCase(): p};
  final pattern = RegExp(
      '(?<![\\p{L}\\p{N}_#])#(${names.map(_escape).join('|')})(?![\\p{L}\\p{N}_-])',
      caseSensitive: false,
      unicode: true);
  final out = <ProjectSegment>[];
  var last = 0;
  for (final m in pattern.allMatches(text)) {
    final project = byName[m[1]!.toLowerCase()];
    if (project == null) continue;
    if (m.start > last) out.add(ProjectSegment(text.substring(last, m.start)));
    out.add(ProjectSegment(m[0]!, project));
    last = m.end;
  }
  if (last < text.length) out.add(ProjectSegment(text.substring(last)));
  return out.isEmpty ? [ProjectSegment(text)] : out;
}
