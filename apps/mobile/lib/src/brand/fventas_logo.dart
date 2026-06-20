import 'package:flutter/material.dart';

class FVENTASLogo extends StatelessWidget {
  const FVENTASLogo({
    super.key,
    this.compact = false,
    this.onDark = false,
    this.size,
  });

  final bool compact;
  final bool onDark;
  final double? size;

  @override
  Widget build(BuildContext context) {
    final markSize = size ?? (compact ? 40 : 42);
    final gray = onDark ? const Color(0xFFE5E7E7) : const Color(0xFF747878);
    final titleStyle = Theme.of(context).textTheme.titleLarge?.copyWith(
          fontWeight: FontWeight.w900,
          letterSpacing: 0,
          height: 0.95,
        );

    return Semantics(
      label: 'FVENTAS',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          CustomPaint(
            size: Size.square(markSize),
            painter: _FVENTASMarkPainter(
              gray: gray,
              compact: compact,
              onDark: onDark,
            ),
          ),
          if (!compact) ...[
            const SizedBox(width: 8),
            RichText(
              text: TextSpan(
                style: titleStyle,
                children: [
                  const TextSpan(
                    text: 'F',
                    style: TextStyle(color: Color(0xFF0D6EFD)),
                  ),
                  TextSpan(text: 'VENTAS', style: TextStyle(color: gray)),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _FVENTASMarkPainter extends CustomPainter {
  const _FVENTASMarkPainter({
    required this.gray,
    required this.compact,
    required this.onDark,
  });

  final Color gray;
  final bool compact;
  final bool onDark;

  @override
  void paint(Canvas canvas, Size size) {
    const deepBlue = Color(0xFF052C65);
    const white = Colors.white;
    const lightBlue = Color(0xFFDBEAFE);
    final whitePaint = Paint()
      ..color = white
      ..isAntiAlias = true;
    final lightPaint = Paint()
      ..color = lightBlue
      ..isAntiAlias = true;
    final dotPaint = Paint()
      ..color = const Color(0xFF93C5FD)
      ..isAntiAlias = true;
    final w = size.width;
    final h = size.height;

    void drawFventasIcon() {
      canvas.save();
      canvas.scale(w / 512, h / 512);

      final background = RRect.fromRectAndRadius(
        const Rect.fromLTWH(0, 0, 512, 512),
        const Radius.circular(118),
      );
      canvas.drawRRect(
        background,
        Paint()
          ..shader = const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF0D6EFD), deepBlue],
          ).createShader(const Rect.fromLTWH(0, 0, 512, 512))
          ..isAntiAlias = true,
      );

      final fPath = Path()
        ..moveTo(126, 148)
        ..lineTo(378, 148)
        ..lineTo(378, 218)
        ..lineTo(204, 218)
        ..lineTo(204, 272)
        ..lineTo(347, 272)
        ..lineTo(347, 338)
        ..lineTo(204, 338)
        ..lineTo(204, 454)
        ..lineTo(126, 454)
        ..close();
      canvas.drawPath(fPath, whitePaint);

      final vPath = Path()
        ..moveTo(262, 268)
        ..lineTo(305, 372)
        ..lineTo(348, 268)
        ..lineTo(426, 268)
        ..lineTo(339, 454)
        ..lineTo(270, 454)
        ..lineTo(183, 268)
        ..close();
      canvas.drawPath(vPath, lightPaint);

      canvas.drawCircle(const Offset(402, 122), 26, dotPaint);
      canvas.restore();
    }

    if (compact) {
      drawFventasIcon();
      return;
    }

    drawFventasIcon();
  }

  @override
  bool shouldRepaint(covariant _FVENTASMarkPainter oldDelegate) {
    return oldDelegate.gray != gray ||
        oldDelegate.compact != compact ||
        oldDelegate.onDark != onDark;
  }
}
