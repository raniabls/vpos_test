import { useEffect, useRef } from 'react'

export default function RobotCanvas({ speaking }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    let raf = 0
    let floatY = 0
    let floatDir = 1
    let blinkT = 0
    let eyeClosed = false
    let mouthOpenCurrent = 0
    let mouthOpenTarget = 0
    let mouthPhase = 0

    function roundRect(x, y, w, h, r) {
      ctx.beginPath()
      ctx.moveTo(x + r, y)
      ctx.lineTo(x + w - r, y)
      ctx.quadraticCurveTo(x + w, y, x + w, y + r)
      ctx.lineTo(x + w, y + h - r)
      ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
      ctx.lineTo(x + r, y + h)
      ctx.quadraticCurveTo(x, y + h, x, y + h - r)
      ctx.lineTo(x, y + r)
      ctx.quadraticCurveTo(x, y, x + r, y)
      ctx.closePath()
    }

    function drawShadow(cx) {
      ctx.save()
      const g = ctx.createRadialGradient(cx, 492, 20, cx, 492, 110)
      g.addColorStop(0, 'rgba(0,0,0,0.18)')
      g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g
      ctx.beginPath()
      ctx.ellipse(cx, 540, 108, 20, 0, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    }

    function drawBody(cx, cy) {
      ctx.save()
      ctx.shadowColor = 'rgba(0,0,0,0.18)'
      ctx.shadowBlur = 24
      ctx.shadowOffsetY = 10

      const g = ctx.createRadialGradient(cx - 26, cy - 48, 8, cx, cy, 120)
      g.addColorStop(0, '#ffffff')
      g.addColorStop(0.45, '#efeff4')
      g.addColorStop(0.78, '#dadbe2')
      g.addColorStop(1, '#c7c8d1')

      ctx.fillStyle = g
      ctx.beginPath()
      ctx.ellipse(cx, cy, 88, 124, 0, 0, Math.PI * 2)
      ctx.fill()

      const gloss = ctx.createRadialGradient(cx - 28, cy - 52, 0, cx - 28, cy - 52, 50)
      gloss.addColorStop(0, 'rgba(255,255,255,0.65)')
      gloss.addColorStop(1, 'rgba(255,255,255,0)')
      ctx.fillStyle = gloss
      ctx.beginPath()
      ctx.ellipse(cx - 24, cy - 46, 34, 24, -0.2, 0, Math.PI * 2)
      ctx.fill()

      ctx.restore()
    }

    function drawArm(ax, ay, side) {
      ctx.save()
      ctx.translate(ax, ay)
      ctx.rotate(side * 0.08)

      ctx.shadowColor = 'rgba(0,0,0,0.14)'
      ctx.shadowBlur = 16
      ctx.shadowOffsetY = 7

      const g = ctx.createRadialGradient(-8 * side, -22, 0, 0, 0, 56)
      g.addColorStop(0, '#ffffff')
      g.addColorStop(0.42, '#efeff4')
      g.addColorStop(0.8, '#d7d8e0')
      g.addColorStop(1, '#c5c7cf')

      ctx.fillStyle = g
      ctx.beginPath()
      ctx.ellipse(0, 0, 28, 66, 0, 0, Math.PI * 2)
      ctx.fill()

      const gloss = ctx.createRadialGradient(-10 * side, -24, 0, -10 * side, -24, 22)
      gloss.addColorStop(0, 'rgba(255,255,255,0.75)')
      gloss.addColorStop(1, 'rgba(255,255,255,0)')
      ctx.fillStyle = gloss
      ctx.beginPath()
      ctx.ellipse(-8 * side, -22, 14, 18, 0, 0, Math.PI * 2)
      ctx.fill()

      ctx.restore()
    }

    function drawHead(cx, cy) {
      ctx.save()
      ctx.shadowColor = 'rgba(0,0,0,0.18)'
      ctx.shadowBlur = 26
      ctx.shadowOffsetY = 12

      const g = ctx.createRadialGradient(cx - 34, cy - 66, 4, cx, cy - 8, 160)
      g.addColorStop(0, '#ffffff')
      g.addColorStop(0.45, '#efeff4')
      g.addColorStop(0.8, '#dadbe2')
      g.addColorStop(1, '#c8c9d2')

      ctx.fillStyle = g
      ctx.beginPath()
      ctx.ellipse(cx, cy, 154, 136, 0, 0, Math.PI * 2)
      ctx.fill()

      const gloss = ctx.createRadialGradient(cx - 36, cy - 82, 0, cx - 36, cy - 82, 54)
      gloss.addColorStop(0, 'rgba(255,255,255,0.72)')
      gloss.addColorStop(1, 'rgba(255,255,255,0)')
      ctx.fillStyle = gloss
      ctx.beginPath()
      ctx.ellipse(cx - 32, cy - 78, 42, 22, -0.15, 0, Math.PI * 2)
      ctx.fill()

      ctx.restore()
    }

    function drawEar(cx, cy, side) {
      const x = cx + side * 156
      const y = cy + 6

      ctx.save()

      ctx.shadowColor = 'rgba(0,0,0,0.12)'
      ctx.shadowBlur = 10
      ctx.shadowOffsetY = 4

      const red = ctx.createRadialGradient(x - side * 10, y - 10, 2, x, y, 44)
      red.addColorStop(0, '#ff5047')
      red.addColorStop(0.45, '#ef1616')
      red.addColorStop(1, '#c70707')
      ctx.fillStyle = red
      ctx.beginPath()
      ctx.ellipse(x, y, 34, 46, 0, 0, Math.PI * 2)
      ctx.fill()

      const whiteX = x - side * 10
      const wg = ctx.createRadialGradient(whiteX - side * 4, y - 4, 0, whiteX, y, 20)
      wg.addColorStop(0, '#ffffff')
      wg.addColorStop(1, '#e9e9ee')
      ctx.fillStyle = wg
      ctx.beginPath()
      ctx.ellipse(whiteX, y, 9, 36, 0, 0, Math.PI * 2)
      ctx.fill()

      ctx.restore()
    }

    function drawFace(cx, cy) {
      ctx.save()

      const face = ctx.createLinearGradient(cx - 120, cy, cx + 120, cy)
      face.addColorStop(0, '#141416')
      face.addColorStop(0.5, '#0e0e11')
      face.addColorStop(1, '#17171b')
      ctx.fillStyle = face

      ctx.beginPath()
      ctx.moveTo(cx - 106, cy - 62)
      ctx.quadraticCurveTo(cx - 92, cy - 78, cx - 68, cy - 78)
      ctx.lineTo(cx - 24, cy - 78)
      ctx.quadraticCurveTo(cx, cy - 92, cx + 24, cy - 78)
      ctx.lineTo(cx + 68, cy - 78)
      ctx.quadraticCurveTo(cx + 92, cy - 78, cx + 106, cy - 62)
      ctx.quadraticCurveTo(cx + 116, cy - 52, cx + 116, cy - 26)
      ctx.lineTo(cx + 116, cy + 34)
      ctx.quadraticCurveTo(cx + 116, cy + 64, cx + 90, cy + 72)
      ctx.quadraticCurveTo(cx + 40, cy + 82, cx, cy + 82)
      ctx.quadraticCurveTo(cx - 40, cy + 82, cx - 90, cy + 72)
      ctx.quadraticCurveTo(cx - 116, cy + 64, cx - 116, cy + 34)
      ctx.lineTo(cx - 116, cy - 26)
      ctx.quadraticCurveTo(cx - 116, cy - 52, cx - 106, cy - 62)
      ctx.closePath()
      ctx.fill()

      ctx.strokeStyle = 'rgba(255,255,255,0.22)'
      ctx.lineWidth = 3
      ctx.stroke()

      ctx.restore()
    }

    function drawEye(ex, ey) {
      ctx.save()

      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 6

      if (eyeClosed) {
        ctx.lineCap = 'round'
        ctx.beginPath()
        ctx.moveTo(ex - 18, ey)
        ctx.lineTo(ex + 18, ey)
        ctx.stroke()
      } else {
        ctx.beginPath()
        ctx.arc(ex, ey, 24, 0, Math.PI * 2)
        ctx.stroke()

        ctx.fillStyle = '#1a1a1f'
        ctx.beginPath()
        ctx.arc(ex, ey, 19, 0, Math.PI * 2)
        ctx.fill()

        ctx.fillStyle = '#ffffff'
        ctx.beginPath()
        ctx.arc(ex - 8, ey - 8, 5, 0, Math.PI * 2)
        ctx.fill()

        ctx.beginPath()
        ctx.arc(ex + 6, ey - 4, 2.5, 0, Math.PI * 2)
        ctx.fill()
      }

      ctx.restore()
    }

function drawMouth(cx, cy) {
  const m = mouthOpenCurrent;

  /* POSITION */
  const mx = cx;
  const my = cy - 8;

  /* SIZE */
  const w = 14 + m * 10;
  const hB = m * 12;
  const hT = m * 3;

  ctx.save();

  /* INSIDE MOUTH */
  if (m > 0.03) {
    ctx.beginPath();

    ctx.moveTo(mx - w, my);

    ctx.bezierCurveTo(
      mx - w * 0.5,
      my + hB,
      mx + w * 0.5,
      my + hB,
      mx + w,
      my
    );

    ctx.bezierCurveTo(
      mx + w * 0.5,
      my - hT,
      mx - w * 0.5,
      my - hT,
      mx - w,
      my
    );

    ctx.closePath();

    const bg = ctx.createRadialGradient(
      mx,
      my + hB * 0.3,
      0,
      mx,
      my + hB,
      w
    );

    bg.addColorStop(0, '#202020');
    bg.addColorStop(1, '#050505');

    ctx.fillStyle = bg;
    ctx.fill();
  }

  /* MAIN WHITE LINE */
  const line = ctx.createLinearGradient(mx - w, my, mx + w, my);

  line.addColorStop(0, '#d9d9d9');
  line.addColorStop(0.5, '#ffffff');
  line.addColorStop(1, '#d9d9d9');

  ctx.strokeStyle = line;
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';

  ctx.beginPath();

  ctx.moveTo(mx - w, my);

  ctx.bezierCurveTo(
    mx - w * 0.5,
    my + hB * 0.9,
    mx + w * 0.5,
    my + hB * 0.9,
    mx + w,
    my
  );

  ctx.stroke();

  /* TOP HIGHLIGHT */
  ctx.strokeStyle = 'rgba(255,255,255,0.45)';
  ctx.lineWidth = 1.2;

  ctx.beginPath();

  ctx.moveTo(mx - w + 2, my - 1);

  ctx.bezierCurveTo(
    mx - w * 0.5,
    my - 3 + m * 2,
    mx + w * 0.5,
    my - 3 + m * 2,
    mx + w - 2,
    my - 1
  );

  ctx.stroke();

  ctx.restore();
}

    function drawRobot() {
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      const cx = canvas.width / 2
      const headCy = 210 + floatY
      const bodyCy = 406 + floatY

      drawShadow(cx)
      drawArm(cx - 115, bodyCy - 18, -1)
      drawArm(cx + 115, bodyCy - 18, 1)
      drawBody(cx, bodyCy)
      drawEar(cx, headCy, -1)
      drawEar(cx, headCy, 1)
      drawHead(cx, headCy)
      drawFace(cx, headCy + 10)
      drawEye(cx - 52, headCy + 4)
      drawEye(cx + 52, headCy + 4)
      drawMouth(cx, headCy + 52)
    }

    function animate() {
      raf = requestAnimationFrame(animate)

      floatY += 0.18 * floatDir
      if (Math.abs(floatY) > 6) floatDir *= -1

      blinkT += 1
      if (blinkT === 160) eyeClosed = true
      if (blinkT === 170) {
        eyeClosed = false
        blinkT = 0
      }

      if (speaking) {
        mouthPhase += 0.4
        mouthOpenTarget = 0.5 + Math.sin(mouthPhase) * 0.6
        mouthOpenTarget = Math.max(0.1, Math.min(1.2, mouthOpenTarget))
      } else {
        mouthOpenTarget = 0
        mouthPhase = 0
      }

      mouthOpenCurrent += (mouthOpenTarget - mouthOpenCurrent) * 0.18

      drawRobot()
    }

    animate()
    return () => cancelAnimationFrame(raf)
  }, [speaking])

  return <canvas id="robot-canvas" ref={canvasRef} width="520" height="560" />
}