import 'package:flutter/material.dart';

class WulkanLogo extends StatelessWidget {
  const WulkanLogo({
    super.key,
    this.compact = false,
    this.onDark = false,
  });

  final bool compact;
  final bool onDark;

  @override
  Widget build(BuildContext context) {
    final gray = onDark ? const Color(0xFFE5E7E7) : const Color(0xFF747878);
    final titleStyle = Theme.of(context).textTheme.titleLarge?.copyWith(
          fontWeight: FontWeight.w900,
          letterSpacing: 0,
          height: 0.95,
        );

    return Semantics(
      label: 'Wulkan',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          CustomPaint(
            size: Size(compact ? 40 : 46, compact ? 40 : 38),
            painter: _WulkanMarkPainter(
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
                    text: 'WUL',
                    style: TextStyle(color: Color(0xFFFF4B00)),
                  ),
                  TextSpan(text: 'KAN', style: TextStyle(color: gray)),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _WulkanMarkPainter extends CustomPainter {
  const _WulkanMarkPainter({
    required this.gray,
    required this.compact,
    required this.onDark,
  });

  final Color gray;
  final bool compact;
  final bool onDark;

  @override
  void paint(Canvas canvas, Size size) {
    final orange = Paint()
      ..color = const Color(0xFFFF4B00)
      ..isAntiAlias = true;
    const blackColor = Color(0xFF090909);
    const whiteColor = Colors.white;
    final base = Paint()
      ..color = gray
      ..isAntiAlias = true;
    final white = Paint()
      ..color = whiteColor
      ..isAntiAlias = true;
    final black = Paint()
      ..color = blackColor
      ..isAntiAlias = true;
    final w = size.width;
    final h = size.height;

    if (compact) {
      final background = RRect.fromRectAndRadius(
        Rect.fromLTWH(0, 0, w, h),
        Radius.circular(w * 0.08),
      );
      canvas.drawRRect(background, black);

      final accent = Path()
        ..moveTo(w * 0.5, h * 0.1)
        ..lineTo(w * 0.68, h * 0.1)
        ..lineTo(w * 0.75, h * 0.42)
        ..lineTo(w * 0.43, h * 0.42)
        ..close();
      canvas.drawPath(accent, orange);

      final slash = Path()
        ..moveTo(w * 0.78, h * 0.08)
        ..lineTo(w * 0.95, h * 0.08)
        ..lineTo(w * 0.79, h * 0.72)
        ..lineTo(w * 0.64, h * 0.72)
        ..close();
      canvas.drawPath(slash, white);

      final arc = Path()
        ..moveTo(w * 0.09, h * 0.93)
        ..cubicTo(w * 0.06, h * 0.54, w * 0.29, h * 0.25, w * 0.78, h * 0.3);
      canvas.drawPath(
        arc,
        Paint()
          ..color = Colors.white
          ..isAntiAlias = true
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round
          ..strokeWidth = w * 0.06,
      );

      final letter = Path()
        ..moveTo(w * 0.18, h * 0.5)
        ..lineTo(w * 0.3, h * 0.78)
        ..lineTo(w * 0.46, h * 0.78)
        ..lineTo(w * 0.52, h * 0.5)
        ..lineTo(w * 0.58, h * 0.78)
        ..lineTo(w * 0.75, h * 0.78)
        ..lineTo(w * 0.84, h * 0.42)
        ..lineTo(w * 0.72, h * 0.42)
        ..lineTo(w * 0.66, h * 0.62)
        ..lineTo(w * 0.61, h * 0.42)
        ..lineTo(w * 0.51, h * 0.42)
        ..lineTo(w * 0.45, h * 0.62)
        ..lineTo(w * 0.4, h * 0.42)
        ..lineTo(w * 0.3, h * 0.42)
        ..lineTo(w * 0.25, h * 0.62)
        ..close();
      canvas.drawPath(letter, white);
      return;
    }

    final flame = Path()
      ..moveTo(w * 0.58, h * 0.06)
      ..lineTo(w * 0.78, h * 0.06)
      ..lineTo(w * 0.64, h * 0.56)
      ..lineTo(w * 0.47, h * 0.56)
      ..close();
    canvas.drawPath(flame, orange);

    final cap = Path()
      ..moveTo(w * 0.49, h * 0.12)
      ..lineTo(w * 0.59, h * 0.12)
      ..lineTo(w * 0.53, h * 0.5)
      ..lineTo(w * 0.41, h * 0.5)
      ..close();
    canvas.drawPath(cap, base);

    final wordMark = Path()
      ..moveTo(w * 0.05, h * 0.54)
      ..lineTo(w * 0.16, h * 0.9)
      ..lineTo(w * 0.29, h * 0.47)
      ..lineTo(w * 0.42, h * 0.9)
      ..lineTo(w * 0.55, h * 0.47)
      ..lineTo(w * 0.68, h * 0.9)
      ..lineTo(w * 0.79, h * 0.54)
      ..lineTo(w * 0.68, h * 0.54)
      ..lineTo(w * 0.58, h * 0.75)
      ..lineTo(w * 0.49, h * 0.54)
      ..lineTo(w * 0.39, h * 0.54)
      ..lineTo(w * 0.3, h * 0.75)
      ..lineTo(w * 0.2, h * 0.54)
      ..close();
    canvas.drawPath(wordMark, onDark ? white : black);

    final arc = Path()
      ..moveTo(w * 0.02, h * 0.82)
      ..cubicTo(w * 0.08, h * 0.47, w * 0.34, h * 0.25, w * 0.68, h * 0.3);
    canvas.drawPath(
      arc,
      Paint()
        ..color = onDark ? whiteColor : blackColor
        ..isAntiAlias = true
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeWidth = w * 0.055,
    );
  }

  @override
  bool shouldRepaint(covariant _WulkanMarkPainter oldDelegate) {
    return oldDelegate.gray != gray || oldDelegate.compact != compact;
  }
}
