interface CircularMeterProps {
  value: number;
  unit?: string;
  secondaryLabel?: string;
  size?: number;
  strokeWidth?: number;
  max?: number;
  color?: string;
  trackColor?: string;
}

/**
 * A simple SVG ring gauge that matches the factory dashboard image:
 * gray ring, teal value in center, optional unit below value.
 */
export function CircularMeter({
  value,
  unit,
  secondaryLabel,
  size = 120,
  strokeWidth = 12,
  max = 0,
  color = '#0d9488',
  trackColor = '#e5e7eb',
}: CircularMeterProps) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = cx - strokeWidth / 2 - 2;
  const circumference = 2 * Math.PI * radius;

  // Fill arc only when a meaningful max is provided
  const pct = max > 0 ? Math.min(value / max, 1) : 0;
  const dashOffset = circumference * (1 - pct);

  // Font sizes scale with circle size
  const valueFontSize = size * 0.18;
  const unitFontSize = size * 0.11;

  return (
    <div className="flex items-center justify-center">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ display: 'block' }}
      >
        {/* Track ring */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={trackColor}
          strokeWidth={strokeWidth}
        />

        {/* Progress arc (only if max > 0 and value > 0) */}
        {max > 0 && value > 0 && (
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            transform={`rotate(-90 ${cx} ${cy})`}
          />
        )}

        {/* Center value */}
        <text
          x={cx}
          y={secondaryLabel || unit ? cy - valueFontSize * 0.3 : cy}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={color}
          fontSize={valueFontSize}
          fontFamily="ui-monospace, SFMono-Regular, monospace"
          fontWeight="600"
        >
          {typeof value === 'number' && !isNaN(value)
            ? value % 1 === 0
              ? value.toString()
              : value.toFixed(1)
            : '-'}
        </text>

        {/* Center secondary label / unit */}
        {(secondaryLabel || unit) && (
          <text
            x={cx}
            y={cy + valueFontSize * 0.9}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={color}
            fontSize={unitFontSize}
            fontFamily="ui-sans-serif, system-ui, sans-serif"
          >
            {secondaryLabel ?? unit}
          </text>
        )}
      </svg>
    </div>
  );
}
