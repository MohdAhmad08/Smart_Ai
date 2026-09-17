import { useEffect, useRef } from 'react';

interface FlowAnimationProps {
  color?: string;
  speed?: number; // px per second
  particleCount?: number;
  direction?: 'horizontal' | 'vertical';
  className?: string;
}

export function FlowAnimation({
  color = '#ffffff',
  speed = 60,
  particleCount = 5,
  direction = 'horizontal',
  className = '',
}: FlowAnimationProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  const particlesRef = useRef<{ x: number; y: number; opacity: number; size: number }[]>([]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    // Initialize particles
    particlesRef.current = Array.from({ length: particleCount }, (_, i) => ({
      x: direction === 'horizontal' ? (canvas.width / particleCount) * i : Math.random() * canvas.width,
      y: direction === 'vertical' ? (canvas.height / particleCount) * i : canvas.height / 2,
      opacity: Math.random() * 0.7 + 0.3,
      size: Math.random() * 2 + 1.5,
    }));

    let last = performance.now();

    const draw = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particlesRef.current.forEach((p, i) => {
        // Move
        if (direction === 'horizontal') {
          p.x += speed * dt;
          if (p.x > canvas.width + 10) {
            p.x = -10;
            p.y = canvas.height / 2 + (Math.random() - 0.5) * 6;
          }
        } else {
          p.y += speed * dt;
          if (p.y > canvas.height + 10) {
            p.y = -10;
            p.x = canvas.width / 2 + (Math.random() - 0.5) * 6;
          }
        }

        // Draw glow
        const gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 3);
        gradient.addColorStop(0, hexToRgba(color, p.opacity));
        gradient.addColorStop(1, hexToRgba(color, 0));
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * 3, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();

        // Draw core dot
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = hexToRgba(color, p.opacity);
        ctx.fill();
      });

      animFrameRef.current = requestAnimationFrame(draw);
    };

    animFrameRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      ro.disconnect();
    };
  }, [color, speed, particleCount, direction]);

  return (
    <canvas
      ref={canvasRef}
      className={`w-full h-full ${className}`}
      style={{ display: 'block' }}
    />
  );
}

function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ─── Inline CSS flow strip (lightweight, no canvas) ──────────────────────────

interface FlowStripProps {
  color: string;
  label?: string;
}

export function FlowStrip({ color, label }: FlowStripProps) {
  return (
    <div className="relative w-full h-4 overflow-hidden rounded-full bg-white/5">
      {/* Glow track */}
      <div
        className="absolute inset-0 rounded-full opacity-20"
        style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
      />
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="absolute top-1/2 -translate-y-1/2 rounded-full"
          style={{
            width: 6,
            height: 6,
            backgroundColor: color,
            boxShadow: `0 0 6px 2px ${color}88`,
            animation: `flowParticle 2s linear infinite`,
            animationDelay: `${i * 0.4}s`,
          }}
        />
      ))}
    </div>
  );
}
