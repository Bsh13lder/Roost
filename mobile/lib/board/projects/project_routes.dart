import 'package:go_router/go_router.dart';

import 'project_page.dart';

/// The app's route for one project's page.
const projectPagePath = '/board/projects/:projectId';

/// Builds `/board/projects/:projectId`.
ProjectPage projectPageFor(GoRouterState state) =>
    ProjectPage(projectId: state.pathParameters['projectId']!);
