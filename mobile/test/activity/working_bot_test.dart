import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/widgets/lens_doing.dart';
import 'package:roost_mobile/widgets/working_bot.dart';

Widget host(Widget child, {bool still = false}) => MaterialApp(
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: still),
          child: Scaffold(body: Center(child: child)),
        ),
      ),
    );

void main() {
  test('every run_step kind maps to what the eyes do, in one place', () {
    expect(doingOf('think'), RobotDoing.think);
    expect(doingOf('other'), RobotDoing.think);
    expect(doingOf('search'), RobotDoing.search);
    expect(doingOf('read'), RobotDoing.read);
    expect(doingOf('computer'), RobotDoing.computer);
    expect(doingOf('program'), RobotDoing.program);
    for (final k in ['file', 'notes', 'message', 'memory']) {
      expect(doingOf(k), RobotDoing.write, reason: k);
    }
    for (final k in ['tasks', 'money', 'calendar', 'bots']) {
      expect(doingOf(k), RobotDoing.records, reason: k);
    }
    expect(doingOf(null), RobotDoing.think);
    expect(doingOf('something new'), RobotDoing.think);
  });

  test('searching scans side to side', () {
    expect(poseFor(RobotDoing.search, 0).pupil.dx, lessThan(0));
    expect(poseFor(RobotDoing.search, 0.25).pupil.dx, greaterThan(0));
  });

  test('reading sweeps left to right along a line, then drops to the next', () {
    final start = poseFor(RobotDoing.read, 0).pupil;
    final end = poseFor(RobotDoing.read, 0.4).pupil;
    final next = poseFor(RobotDoing.read, 0.5).pupil;
    expect(end.dx, greaterThan(start.dx));
    expect(end.dy, closeTo(start.dy, 0.01));
    expect(next.dy, greaterThan(start.dy));
  });

  test('the computer and writing look down; records glance down then nod', () {
    expect(poseFor(RobotDoing.computer, 0.3).pupil.dy, greaterThan(1));
    expect(poseFor(RobotDoing.write, 0.1).pupil.dy, greaterThan(1));
    expect(poseFor(RobotDoing.write, 0.7).pupil.dx, greaterThan(poseFor(RobotDoing.write, 0).pupil.dx));
    expect(poseFor(RobotDoing.records, 0.4).pupil.dy, greaterThan(1));
    expect(poseFor(RobotDoing.records, 0.75).nod, greaterThan(0));
    expect(poseFor(RobotDoing.records, 0.4).nod, 0);
  });

  test('thinking glances up with a tilt; a program whirrs round', () {
    final think = poseFor(RobotDoing.think, 0.25);
    expect(think.pupil.dy, lessThan(0));
    expect(think.tilt, isNot(0));
    expect(poseFor(RobotDoing.program, 0).pupil, isNot(poseFor(RobotDoing.program, 0.0625).pupil));
  });

  test('the head bobs gently while it works', () {
    expect(poseFor(RobotDoing.search, 0.25).bob, isNot(poseFor(RobotDoing.search, 0.75).bob));
  });

  test('standing still keeps the kind\'s look but no motion', () {
    final still = stillPose(RobotDoing.write);
    expect(still.pupil.dy, greaterThan(1));
    expect(still.tilt, 0);
    expect(still.bob, 0);
  });

  testWidgets('a working bot draws its robot and moves', (tester) async {
    await tester.pumpWidget(host(const WorkingBot(avatar: Avatar(), kind: 'search')));
    expect(find.byKey(const Key('working-bot')), findsOneWidget);
    expect(tester.hasRunningAnimations, isTrue);
    await tester.pumpWidget(host(const SizedBox()));
  });

  testWidgets('with less motion it stands still', (tester) async {
    await tester.pumpWidget(host(const WorkingBot(avatar: Avatar(), kind: 'read'), still: true));
    expect(find.byKey(const Key('working-bot')), findsOneWidget);
    expect(tester.hasRunningAnimations, isFalse);
  });
}
