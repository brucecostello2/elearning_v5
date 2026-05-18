import React from 'react';
import { AbsoluteFill, useCurrentFrame, spring,
         interpolate, useVideoConfig } from 'remotion';

interface LowerThirdProps {
  name: string;
  title: string;
  durationFrames: number;
  accentColor?: string;
}

export const LowerThird: React.FC<LowerThirdProps> = ({
  name, title, durationFrames, accentColor = '#e07800',
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Slide in from left
  const slideX = spring({
    frame, fps, from: -400, to: 0,
    config: { damping: 25, stiffness: 300 },
  });

  // Name appears first, title follows
  const nameOpacity = interpolate(frame, [0, 10], [0, 1],
    { extrapolateRight: 'clamp' });
  const titleOpacity = interpolate(frame, [10, 25], [0, 1],
    { extrapolateRight: 'clamp' });

  // Fade out
  const opacity = interpolate(
    frame,
    [durationFrames - 12, durationFrames - 3],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div style={{
        position: 'absolute', bottom: 120, left: 80,
        transform: `translateX(${slideX}px)`,
        opacity,
      }}>
        {/* Background bar */}
        <div style={{
          background: 'rgba(0, 0, 0, 0.85)',
          padding: '12px 20px 12px 16px',
          borderLeft: `5px solid ${accentColor}`,
          display: 'inline-block', minWidth: 300,
        }}>
          <div style={{
            fontSize: 32, fontWeight: 700, color: '#ffffff',
            fontFamily: 'Georgia, serif', opacity: nameOpacity,
          }}>
            {name}
          </div>
          <div style={{
            fontSize: 20, color: accentColor,
            fontFamily: 'Georgia, serif', marginTop: 4,
            opacity: titleOpacity,
          }}>
            {title}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
