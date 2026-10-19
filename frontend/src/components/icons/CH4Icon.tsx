import React from 'react';

interface CH4IconProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
}

/**
 * Ball-and-stick CH4 (methane) tetrahedral molecular icon.
 * Features a central filled carbon atom with 4 filled hydrogen atoms
 * connected via cylindrical bond sticks.
 */
export default function CH4Icon({
  size = 20,
  className = '',
  ...props
}: CH4IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      {...props}
    >
      {/* 4 Bond Sticks */}
      <line
        x1="12"
        y1="11"
        x2="12"
        y2="3.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <line
        x1="12"
        y1="11"
        x2="4.5"
        y2="16"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <line
        x1="12"
        y1="11"
        x2="19.5"
        y2="16"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <line
        x1="12"
        y1="11"
        x2="12"
        y2="20"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />

      {/* 4 Outer Hydrogen Atoms (Filled Balls) */}
      <circle cx="12" cy="3.5" r="2.2" fill="currentColor" />
      <circle cx="4.5" cy="16" r="2.2" fill="currentColor" />
      <circle cx="19.5" cy="16" r="2.2" fill="currentColor" />
      <circle cx="12" cy="20" r="2.2" fill="currentColor" />

      {/* Central Carbon Atom (Larger Filled Ball) */}
      <circle cx="12" cy="11" r="3.4" fill="currentColor" />
    </svg>
  );
}
