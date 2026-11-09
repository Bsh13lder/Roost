import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../theme/tokens.dart';
import '../common/format.dart';
import '../common/widgets.dart';
import 'projects_api.dart';

/// The Board's Projects tab: pinned first, each with its bars as the server
/// reckons them. A row opens `/board/projects/:projectId`.
class ProjectsTab extends ConsumerStatefulWidget {
  const ProjectsTab({super.key});

  @override
  ConsumerState<ProjectsTab> createState() => _ProjectsTabState();
}

class _ProjectsTabState extends ConsumerState<ProjectsTab> {
  late Future<List<Json>> _projects = ref.read(projectsApiProvider).list();

  void _reload() => setState(() => _projects = ref.read(projectsApiProvider).list());

  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: _projects,
      builder: (context, snap) {
        if (snap.hasError) return BoardNote(errorText(snap.error!), error: true);
        if (!snap.hasData) return const BoardNote('Loading…');
        final projects = snap.data!;
        if (projects.isEmpty) {
          return const BoardNote('No projects yet. Ask a bot to start one.');
        }
        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView.builder(
            itemCount: projects.length,
            itemBuilder: (_, i) => ProjectCard(
              project: projects[i],
              onTap: () => context.push('/board/projects/${projects[i]['id']}'),
            ),
          ),
        );
      },
    );
  }
}

/// One project in the list: name, status, the total and monthly bars, tasks.
class ProjectCard extends StatelessWidget {
  const ProjectCard({super.key, required this.project, required this.onTap});

  final Json project;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final p = project;
    final currency = p['currency'] as String;
    final total = p['total'] as Map;
    final month = p['month'] as Map;
    final progress = p['progress'] as Map;
    return Card(
      color: Tokens.panel,
      margin: const EdgeInsets.symmetric(
          horizontal: Tokens.space4, vertical: Tokens.space2),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(Tokens.space4),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              CircleAvatar(radius: 5, backgroundColor: hexColor(p['color'] as String?)),
              const SizedBox(width: Tokens.space2),
              Expanded(
                child: Text('${p['pinned'] == true ? '📌 ' : ''}${p['name']}',
                    style: const TextStyle(fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
              ),
              if (p['status'] == 'archived')
                const Text('Archived', style: TextStyle(color: Tokens.textFaint)),
            ]),
            if (total['budget'] != null) _bar('Total', total, currency),
            if (month['budget'] != null) _bar('This month', month, currency),
            if (total['budget'] == null && month['budget'] == null)
              Text('${formatMoney('${total['spent']}', currency)} spent · no limit',
                  style: const TextStyle(color: Tokens.textSecondary)),
            const SizedBox(height: Tokens.space2),
            Text('${progress['done']} of ${progress['total']} tasks done'
                '${(progress['overdue'] as int) > 0 ? ' · ${progress['overdue']} overdue' : ''}',
                style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          ]),
        ),
      ),
    );
  }

  Widget _bar(String label, Map line, String currency) {
    final remaining = '${line['remaining'] ?? '0'}';
    final over = remaining.startsWith('-');
    final words = over
        ? 'over by ${formatMoney(unsigned(remaining), currency)}'
        : '${formatMoney(remaining, currency)} left of ${formatMoney('${line['budget']}', currency)}';
    return Padding(
      padding: const EdgeInsets.only(top: Tokens.space2),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('$label · $words',
            style: TextStyle(
                color: over ? Tokens.dangerText : Tokens.textSecondary,
                fontSize: Tokens.fsLabel)),
        const SizedBox(height: 4),
        ToneBar(percent: line['used_percent'] as num?, tone: line['tone'] as String?),
      ]),
    );
  }
}
