import React from 'react';
import { AbsoluteFill, useCurrentFrame, spring,
         useVideoConfig, interpolate } from 'remotion';

interface TitleCardProps {
  title: string;
  subtitle?: string;
  theme?: 'dark' | 'light' | 'amber';
  durationFrames: number;
}

const THEMES = {
  dark: { bg: '#0d0d0d', title: '#ffffff', subtitle: '#aaaaaa',
          accent: '#e07800' },
  light: { bg: '#f5f5f5', title: '#111111', subtitle: '#555555',
           accent: '#e07800' },
  amber: { bg: '#1a0900', title: '#ffcc44', subtitle: '#cc8822',
           accent: '#e07800' },
};

export const TitleCard: React.FC<TitleCardProps> = ({
  title, subtitle, theme = 'dark', durationFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = spring({
    frame, fps, from: 0, to: 1,
    config: { damping: 20, stiffness: 200 },
  });

  const titleY = interpolate(frame, [0, 20], [40, 0],
    { extrapolateRight: 'clamp' });

  const subtitleOpacity = spring({
    frame: frame - 10, fps, from: 0, to: 1,
    config: { damping: 20, stiffness: 150 },
  });

  // Fade out near end
  const fadeOut = interpolate(
    frame,
    [durationFrames - 15, durationFrames - 5],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );

  const colors = THEMES[theme];

  return (
    <AbsoluteFill style={{ background: colors.bg, justifyContent: 'center',
                            alignItems: 'center', opacity: fadeOut }}>
      {/* Accent bar */}
      <div style={{
        position: 'absolute', left: 80, top: '50%',
        transform: 'translateY(-60px)',
        width: 4, height: 80,
        background: colors.accent,
        opacity: titleOpacity,
      }} />

      <div style={{
        paddingLeft: 100, maxWidth: 1000,
        transform: `translateY(${titleY}px)`,
        opacity: titleOpacity,
      }}>
        <div style={{
          fontSize: 72, fontWeight: 800, color: colors.title,
          fontFamily: 'Georgia, serif', lineHeight: 1.1,
          marginBottom: 20,
        }}>
          {title}
        </div>
        {subtitle && (
          <div style={{
            fontSize: 36, color: colors.subtitle,
            fontFamily: 'Georgia, serif', opacity: subtitleOpacity,
          }}>
            {subtitle}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
